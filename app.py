import base64
import json
import os
from copy import deepcopy
from threading import Thread

import requests
from cfenv import AppEnv
from flask import Flask, jsonify, request

app = Flask(__name__)

xsuaa_service, destination_service, connectivity_service = 'uaa', 'destination', 'connectivity'


def call_destination(destination: "name of the destination item on the SAP Cloud Platform Cockpit Destinations" = '',
                     path: "endpoint path for accessing the data" = None,
                     env: "CF App Environment Variable" = AppEnv(),
                     requestContentType: "Content type of the request -> Default is always everything" = 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3',
                     stream: "To stream a large file" = False):
    """
    Function to call the on-prem service via destination, connectivity, and Cloud Connector.
    Destination to be fetched can be informed on the call. If no destination could be defined, it will return a 400.

    :param destination: name of the destination item on the SAP Cloud Platform Cockpit Destinations
    :param path: endpoint path for accessing the data
    :param request: request object from flask
    :param env: CF environment object
    :param requestContentType: Content type of the request -> Default is always everything

    :return: data from the end point
    """

    if destination == '':
        return ("Destination not found", 400)
    elif path is None:
        return ("Path not found", 400)
    elif env is None:
        return ("Environment object is not forwarded", 400)

    try:
        vs_uaa_service_credentials = env.get_service(
            name=xsuaa_service).credentials
        vs_connectivity_credentials = env.get_service(
            name=connectivity_service).credentials
        vs_destination_credentials = env.get_service(
            name=destination_service).credentials
    except Exception as err:
        msg = 'Required services not found! Without services / credentials it will be impossible to succeed!' + \
            ' Exception:' + str(err)
        return (msg, 503)
    # ------------------------------------------------------------------------------------------------------------------
    uaa_url = vs_uaa_service_credentials["url"] + \
        '/oauth/token?grant_type=client_credentials'
    try:
        response = requests.post(uaa_url,
                                 headers={'Accept': 'application/json'},
                                 auth=(vs_destination_credentials['clientid'],
                                       vs_destination_credentials['clientsecret']))
        jwt_destination = response.json()['access_token']
    except Exception as err:
        msg = "Something wrong getting JWT from xsuaa service for the destination service. Exception: " + \
            str(err)
        return (msg, 500)

    # ------------------------------------------------------------------------------------------------------------------
    destination_url = vs_destination_credentials['uri'] + '/destination-configuration/v1/destinations/' + \
        destination
    try:
        response = requests.get(destination_url,
                                headers={'Accept': 'application/json', 'Authorization': 'Bearer ' + jwt_destination, })
        destination = response.json()['destinationConfiguration']
        print_version = deepcopy(destination)
        print_version['Password'] = '--protected--'
    except Exception as e:
        msg = "Something wrong reading data from the destination service: " + \
            str(e)
        return (msg, 500)

    # ------------------------------------------------------------------------------------------------------------------
    connectivity_url = vs_uaa_service_credentials["url"] + \
        '/oauth/token?grant_type=client_credentials'
    try:
        response = requests.post(connectivity_url,
                                 headers={'Accept': 'application/json'},
                                 auth=(vs_connectivity_credentials['clientid'],
                                       vs_connectivity_credentials['clientsecret']))
        jwt_connectivity = response.json()['access_token']
    except Exception as e:
        msg = "Something wrong posting data for the connectivity service. Exception: " + \
            str(e)
        return msg, 500

    # ------------------------------------------------------------------------------------------------------------------
    proxies = {'http': "http://" + vs_connectivity_credentials['onpremise_proxy_host'] + ':' +
               vs_connectivity_credentials['onpremise_proxy_port'], }

    request_url = destination['URL'] + path

    # ------------------------------------------------------------------------------------------------------------------
    try:
        if stream:
            response_stream = requests.get(request_url, proxies=proxies, headers={
                'Accept': requestContentType,
                # 'SAP-Connectivity-Authentication': 'Bearer ' + jwt_user_auth,
                'Proxy-Authorization': 'Bearer ' + jwt_connectivity,
                "SAP-Connectivity-SCC-Location_ID": destination["CloudConnectorLocationId"]
            }, auth=(destination['User'], destination['Password']), stream=True)
            return response_stream
        else:
            response = requests.get(request_url, proxies=proxies, headers={
                'Accept': requestContentType,
                # 'SAP-Connectivity-Authentication': 'Bearer ' + jwt_user_auth,
                'Proxy-Authorization': 'Bearer ' + jwt_connectivity,
                "SAP-Connectivity-SCC-Location_ID": destination["CloudConnectorLocationId"]
            }, auth=(destination['User'], destination['Password']))
            return response.content

    except Exception as e:
        msg = "Something wrong when accessing on-premise resource. Exception: " + \
            str(e)
        return (msg, 500)


def download_large_file(destination, responseObject):
    response_stream = call_destination(destination, '/'+'/'.join(
        responseObject["download_url"].strip("https://").split('/')[1:]), stream=True)
    print(response_stream)
    with open(responseObject["name"], 'wb') as fp:
        for chunk in response_stream.iter_content(chunk_size=1024):
            fp.write(chunk)


def download_directory(destination, directory_path, env=AppEnv()):
    responseText = call_destination(destination, directory_path, env)
    print(responseText)
    directory = json.loads(responseText)
    for item in directory:
        if(item["type"] == "file"):
            if item["size"]//1024 >= 1024:
                response_stream = call_destination(
                    destination, '/'+'/'.join(item["download_url"].strip("https://").split('/')[1:]), stream=True)
                print(response_stream)
                with open(item["name"], 'wb') as fp:
                    for chunk in response_stream.iter_content(chunk_size=1024):
                        fp.write(chunk)
            else:
                responseObject = json.loads(call_destination(
                    destination, directory_path + "/" + item["name"]))
                if "raw_lfs" in responseObject["download_url"]:
                    thread = Thread(target=download_large_file,
                                    args=(destination, responseObject,))
                    thread.start()
                else:
                    with open(responseObject["name"], 'wb') as fp:
                        fp.write(base64.standard_b64decode(
                            responseObject["content"]))
        elif(item["type"] == "dir"):
            os.mkdir(item["name"])
            os.chdir(item["name"])
            download_directory(destination, directory_path +
                               "/" + item["name"], env)
            os.chdir('..')


@app.route('/getData', methods=['GET'])
def process_file():
    dest = request.args.get("destination")
    path = request.args.get("path")
    responseText = call_destination(dest, path, AppEnv())
    return responseText

# Routes
@app.route('/downloadDir', methods=['GET'])
def down_dir():
    dest = request.args.get("destination")
    path = request.args.get("path")
    if(dest == None or path == None):
        return "Please provide paramenters"
    download_directory(dest, path, AppEnv())
    dir_list = []
    for root, dirs, files in os.walk('.'):
        for d in dirs:
            dir_list.append(os.path.join(root, d))
        for f in files:
            dir_list.append(os.path.join(root, f))
    return str(''.join(list(os.popen("ls -lh 124M/run1"))))
# Routes
@app.route('/test', methods=['GET','POST'])
def test():
    print(request.data)
    return "HI"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=True)
