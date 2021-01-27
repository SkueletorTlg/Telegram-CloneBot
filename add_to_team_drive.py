from __future__ import print_function
from google.oauth2.service_account import Credentials
import googleapiclient.discovery, json, progress.bar, glob, sys, argparse, time
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import os, pickle

stt = time.time()

parse = argparse.ArgumentParser(
    description='Una herramienta para agregar cuentas de servicio a una unidad compartida desde una carpeta que contiene archivos de credenciales.')
parse.add_argument('--path', '-p', default='accounts',
                   help='Especifique una ruta alternativa a la carpeta de cuentas de servicio.')
parse.add_argument('--credentials', '-c', default='./credentials.json',
                   help='Especifique la ruta relativa para el archivo de credenciales.')
parse.add_argument('--yes', '-y', default=False, action='store_true', help='Omite el aviso de cordura.')
parsereq = parse.add_argument_group('required arguments')
parsereq.add_argument('--drive-id', '-d', help='El ID de la unidad compartida.', required=True)

args = parse.parse_args()
acc_dir = args.path
did = args.drive_id
credentials = glob.glob(args.credentials)

try:
    open(credentials[0], 'r')
    print('>> Credenciales encontradas.')
except IndexError:
    print('>> No se encontraron credenciales.')
    sys.exit(0)

if not args.yes:
    # input('Make sure the following client id is added to the shared drive as Manager:\n' + json.loads((open(
    # credentials[0],'r').read()))['installed']['client_id'])
    input('>> Asegúrese de que la **cuenta de Google** haya generado credentials.json\n   se agrega a tu unidad de equipo '
          '(unidad compartida) como gerente\n>> (Pulse cualquier tecla para continuar)')

creds = None
if os.path.exists('token_sa.pickle'):
    with open('token_sa.pickle', 'rb') as token:
        creds = pickle.load(token)
# If there are no (valid) credentials available, let the user log in.
if not creds or not creds.valid:
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    else:
        flow = InstalledAppFlow.from_client_secrets_file(credentials[0], scopes=[
            'https://www.googleapis.com/auth/admin.directory.group',
            'https://www.googleapis.com/auth/admin.directory.group.member'
        ])
        # creds = flow.run_local_server(port=0)
        creds = flow.run_console()
    # Save the credentials for the next run
    with open('token_sa.pickle', 'wb') as token:
        pickle.dump(creds, token)

drive = googleapiclient.discovery.build("drive", "v3", credentials=creds)
batch = drive.new_batch_http_request()

aa = glob.glob('%s/*.json' % acc_dir)
pbar = progress.bar.Bar("Preparando cuentas", max=len(aa))
for i in aa:
    ce = json.loads(open(i, 'r').read())['client_email']
    batch.add(drive.permissions().create(fileId=did, supportsAllDrives=True, body={
        "role": "fileOrganizer",
        "type": "user",
        "emailAddress": ce
    }))
    pbar.next()
pbar.finish()
print('Añadiendo...')
batch.execute()

print('Completado.')
hours, rem = divmod((time.time() - stt), 3600)
minutes, sec = divmod(rem, 60)
print("Tiempo transcurrido:\n{:0>2}:{:0>2}:{:05.2f}".format(int(hours), int(minutes), sec))
