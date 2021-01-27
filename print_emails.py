import json, os, glob
from bot.config import USE_SERVICE_ACCOUNTS
path = 'accounts'
strr= ''

if USE_SERVICE_ACCOUNTS and os.path.exists(os.path.join(os.getcwd(), path)):
    for count, file in enumerate(glob.glob(os.path.join(os.getcwd(), path, '*.json'))):
        x = json.load(open(file, 'rb'))
        strr += x['client_email'] + ', '
        
        if (count + 1)% 10 == 0:
            strr = strr[:-2]
            strr += '\n\n'
            strr += '-------------------------------------\n\n'
    strr = strr[:-3]
    print(strr)
else:
    print('Establezca `USE_SERVICE_ACCOUNTS` en True en el archivo config.py.')
