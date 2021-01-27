import errno
import os
import pickle
import sys
from argparse import ArgumentParser
from base64 import b64decode
from glob import glob
from json import loads
from random import choice
from time import sleep

from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

SCOPES = ['https://www.googleapis.com/auth/drive', 'https://www.googleapis.com/auth/cloud-platform',
          'https://www.googleapis.com/auth/iam']
project_create_ops = []
current_key_dump = []
sleep_time = 30


# Create count SAs in project
def _create_accounts(service, project, count):
    batch = service.new_batch_http_request(callback=_def_batch_resp)
    for i in range(count):
        aid = _generate_id('mfc-')
        batch.add(service.projects().serviceAccounts().create(name='projects/' + project, body={'accountId': aid,
                                                                                                'serviceAccount': {
                                                                                                    'displayName': aid}}))
    batch.execute()


# Create accounts needed to fill project
def _create_remaining_accounts(iam, project):
    print('Creando cuentas en %s' % project)
    sa_count = len(_list_sas(iam, project))
    while sa_count != 100:
        _create_accounts(iam, project, 100 - sa_count)
        sa_count = len(_list_sas(iam, project))


# Generate a random id
def _generate_id(prefix='saf-'):
    chars = '-abcdefghijklmnopqrstuvwxyz1234567890'
    return prefix + ''.join(choice(chars) for _ in range(25)) + choice(chars[1:])


# List projects using service
def _get_projects(service):
    return [i['projectId'] for i in service.projects().list().execute()['projects']]


# Default batch callback handler
def _def_batch_resp(id, resp, exception):
    if exception is not None:
        if str(exception).startswith('<HttpError 429'):
            sleep(sleep_time / 100)
        else:
            print(str(exception))


# Project Creation Batch Handler
def _pc_resp(id, resp, exception):
    global project_create_ops
    if exception is not None:
        print(str(exception))
    else:
        for i in resp.values():
            project_create_ops.append(i)


# Project Creation
def _create_projects(cloud, count):
    global project_create_ops
    batch = cloud.new_batch_http_request(callback=_pc_resp)
    new_projs = []
    for i in range(count):
        new_proj = _generate_id()
        new_projs.append(new_proj)
        batch.add(cloud.projects().create(body={'project_id': new_proj}))
    batch.execute()

    for i in project_create_ops:
        while True:
            resp = cloud.operations().get(name=i).execute()
            if 'done' in resp and resp['done']:
                break
            sleep(3)
    return new_projs


# Enable services ste for projects in projects
def _enable_services(service, projects, ste):
    batch = service.new_batch_http_request(callback=_def_batch_resp)
    for i in projects:
        for j in ste:
            batch.add(service.services().enable(name='projects/%s/services/%s' % (i, j)))
    batch.execute()


# List SAs in project
def _list_sas(iam, project):
    resp = iam.projects().serviceAccounts().list(name='projects/' + project, pageSize=100).execute()
    if 'accounts' in resp:
        return resp['accounts']
    return []


# Create Keys Batch Handler
def _batch_keys_resp(id, resp, exception):
    global current_key_dump
    if exception is not None:
        current_key_dump = None
        sleep(sleep_time / 100)
    elif current_key_dump is None:
        sleep(sleep_time / 100)
    else:
        current_key_dump.append((
            resp['name'][resp['name'].rfind('/'):],
            b64decode(resp['privateKeyData']).decode('utf-8')
        ))


# Create Keys
def _create_sa_keys(iam, projects, path):
    global current_key_dump
    for i in projects:
        current_key_dump = []
        print('Descargando claves de %s' % i)
        while current_key_dump is None or len(current_key_dump) != 100:
            batch = iam.new_batch_http_request(callback=_batch_keys_resp)
            total_sas = _list_sas(iam, i)
            for j in total_sas:
                batch.add(iam.projects().serviceAccounts().keys().create(
                    name='projects/%s/serviceAccounts/%s' % (i, j['uniqueId']),
                    body={
                        'privateKeyType': 'TYPE_GOOGLE_CREDENTIALS_FILE',
                        'keyAlgorithm': 'KEY_ALG_RSA_2048'
                    }
                ))
            batch.execute()
            if current_key_dump is None:
                print('Descargando claves de %s' % i)
                current_key_dump = []
            else:
                index = 0
                for j in current_key_dump:
                    with open(f'{path}/{index}.json', 'w+') as f:
                        f.write(j[1])
                    index += 1


# Delete Service Accounts
def _delete_sas(iam, project):
    sas = _list_sas(iam, project)
    batch = iam.new_batch_http_request(callback=_def_batch_resp)
    for i in sas:
        batch.add(iam.projects().serviceAccounts().delete(name=i['name']))
    batch.execute()


def serviceaccountfactory(
        credentials='credentials.json',
        token='token_sa.pickle',
        path=None,
        list_projects=False,
        list_sas=None,
        create_projects=None,
        max_projects=12,
        enable_services=None,
        services=['iam', 'drive'],
        create_sas=None,
        delete_sas=None,
        download_keys=None
):
    selected_projects = []
    proj_id = loads(open(credentials, 'r').read())['installed']['project_id']
    creds = None
    if os.path.exists(token):
        with open(token, 'rb') as t:
            creds = pickle.load(t)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(credentials, SCOPES)

            # creds = flow.run_local_server(port=0)
            creds = flow.run_console()

        with open(token, 'wb') as t:
            pickle.dump(creds, t)

    cloud = build('cloudresourcemanager', 'v1', credentials=creds)
    iam = build('iam', 'v1', credentials=creds)
    serviceusage = build('serviceusage', 'v1', credentials=creds)

    projs = None
    while projs == None:
        try:
            projs = _get_projects(cloud)
        except HttpError as e:
            if loads(e.content.decode('utf-8'))['error']['status'] == 'PERMISSION_DENIED':
                try:
                    serviceusage.services().enable(
                        name='projects/%s/services/cloudresourcemanager.googleapis.com' % proj_id).execute()
                except HttpError as e:
                    print(e._get_reason())
                    input('Presione Enter para volver a intentarlo.')
    if list_projects:
        return _get_projects(cloud)
    if list_sas:
        return _list_sas(iam, list_sas)
    if create_projects:
        print("crear proyectos: {}".format(create_projects))
        if create_projects > 0:
            current_count = len(_get_projects(cloud))
            if current_count + create_projects <= max_projects:
                print('Creando %d proyectos' % (create_projects))
                nprjs = _create_projects(cloud, create_projects)
                selected_projects = nprjs
            else:
                sys.exit('No, tú no puedes crear %d proyectos nuevos (s).\n'
                         'Reduzca el valor de --quick-setup.\n'
                         'Recuerda que puedes crear totalmente %d proyectos (%d already).\n'
                         'No elimine proyectos existentes a menos que sepa lo que está haciendo' % (
                             create_projects, max_projects, current_count))
        else:
            print('Sobrescribirá todas las cuentas de servicio en proyectos existentes..\n'
                  'Así que asegúrate de tener algunos proyectos.')
            input("Presione Enter para continuar...")

    if enable_services:
        ste = []
        ste.append(enable_services)
        if enable_services == '~':
            ste = selected_projects
        elif enable_services == '*':
            ste = _get_projects(cloud)
        services = [i + '.googleapis.com' for i in services]
        print('Activando servicios')
        _enable_services(serviceusage, ste, services)
    if create_sas:
        stc = []
        stc.append(create_sas)
        if create_sas == '~':
            stc = selected_projects
        elif create_sas == '*':
            stc = _get_projects(cloud)
        for i in stc:
            _create_remaining_accounts(iam, i)
    if download_keys:
        try:
            os.mkdir(path)
        except OSError as e:
            if e.errno == errno.EEXIST:
                pass
            else:
                raise
        std = []
        std.append(download_keys)
        if download_keys == '~':
            std = selected_projects
        elif download_keys == '*':
            std = _get_projects(cloud)
        _create_sa_keys(iam, std, path)
    if delete_sas:
        std = []
        std.append(delete_sas)
        if delete_sas == '~':
            std = selected_projects
        elif delete_sas == '*':
            std = _get_projects(cloud)
        for i in std:
            print('Eliminando cuentas de servicio en %s' % i)
            _delete_sas(iam, i)


if __name__ == '__main__':
    parse = ArgumentParser(description='Una herramienta para crear cuentas de servicio de Google.')
    parse.add_argument('--path', '-p', default='accounts',
                       help='Especifique un directorio alternativo para generar los archivos de credenciales.')
    parse.add_argument('--token', default='token_sa.pickle', help='Especifique la ruta del archivo de token de pickle.')
    parse.add_argument('--credentials', default='credentials.json', help='Especifique la ruta del archivo de credenciales.')
    parse.add_argument('--list-projects', default=False, action='store_true',
                       help='Lista de proyectos visibles para el usuario.')
    parse.add_argument('--list-sas', default=False, help='Enumere las cuentas de servicio en un proyecto.')
    parse.add_argument('--create-projects', type=int, default=None, help='Crea hasta N proyectos.')
    parse.add_argument('--max-projects', type=int, default=12, help='Cantidad máxima de proyecto permitida. Por defecto: 12')
    parse.add_argument('--enable-services', default=None,
                       help='Habilita servicios en el proyecto. Predeterminado: IAM y Drive')
    parse.add_argument('--services', nargs='+', default=['iam', 'drive'],
                       help='Especifique un conjunto diferente de servicios para habilitar. Reemplaza el predeterminado.')
    parse.add_argument('--create-sas', default=None, help='Crea cuentas de servicio en un proyecto.')
    parse.add_argument('--delete-sas', default=None, help='Eliminar cuentas de servicio en un proyecto.')
    parse.add_argument('--download-keys', default=None, help='Descargue claves para todas las cuentas de servicio en un proyecto.')
    parse.add_argument('--quick-setup', default=None, type=int,
                       help='Cree proyectos, habilite servicios, cree cuentas de servicio y descargue claves. ')
    parse.add_argument('--new-only', default=False, action='store_true', help='No utilice proyectos existentes.')
    args = parse.parse_args()
    # If credentials file is invalid, search for one.
    if not os.path.exists(args.credentials):
        options = glob('*.json')
        print('No se encontraron credenciales en %s. Habilite la API de Drive en:\n'
              'https://developers.google.com/drive/api/v3/quickstart/python\n'
              'y guarde el archivo json como credentials.json' % args.credentials)
        if len(options) < 1:
            exit(-1)
        else:
            i = 0
            print('Seleccione un archivo de credenciales a continuación.')
            inp_options = [str(i) for i in list(range(1, len(options) + 1))] + options
            while i < len(options):
                print('  %d) %s' % (i + 1, options[i]))
                i += 1
            inp = None
            while True:
                inp = input('> ')
                if inp in inp_options:
                    break
            if inp in options:
                args.credentials = inp
            else:
                args.credentials = options[int(inp) - 1]
            print('Usa --credentials %s la próxima vez que use este archivo de credenciales.' % args.credentials)
    if args.quick_setup:
        opt = '*'
        if args.new_only:
            opt = '~'
        args.services = ['iam', 'drive']
        args.create_projects = args.quick_setup
        args.enable_services = opt
        args.create_sas = opt
        args.download_keys = opt
    resp = serviceaccountfactory(
        path=args.path,
        token=args.token,
        credentials=args.credentials,
        list_projects=args.list_projects,
        list_sas=args.list_sas,
        create_projects=args.create_projects,
        max_projects=args.max_projects,
        create_sas=args.create_sas,
        delete_sas=args.delete_sas,
        enable_services=args.enable_services,
        services=args.services,
        download_keys=args.download_keys
    )
    if resp is not None:
        if args.list_projects:
            if resp:
                print('Proyectos (%d):' % len(resp))
                for i in resp:
                    print('  ' + i)
            else:
                print('Sin proyectos.')
        elif args.list_sas:
            if resp:
                print('Cuentas de servicio en %s (%d):' % (args.list_sas, len(resp)))
                for i in resp:
                    print('  %s (%s)' % (i['email'], i['uniqueId']))
            else:
                print('Sin cuentas de servicio.')
