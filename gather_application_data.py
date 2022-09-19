#!/usr/bin/env python3
import os
import requests
import sys
import base64
import json
import time
import datetime
import xml.etree.ElementTree as ET
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()


def init_vars():
    # initialize the environmental variables for this session
    jss = os.environ.get("JSS")
    api_user = os.environ.get("JSSUSER")
    api_pw = os.environ.get("JSSPASS")
    server_type = os.environ.get("SERVERTYPE")
    home = str(Path.home())
    if server_type == "windows":
        json_path = f"{home}\\JamfAPISync\\"
        log_folder_path = f"{json_path}\\Logs\\"
        tmp_path = f"{json_path}\\tmp\\"
    else:
        json_path = f"{home}/JamfAPISync/"
        log_folder_path = f"{json_path}/Logs/"
        tmp_path = f"{json_path}/tmp/"
    debug_mode_tf = True
    test_mode_tf = False
    return jss, api_user, api_pw, json_path, log_folder_path, tmp_path, debug_mode_tf, test_mode_tf


def generate_auth_token():
    # generate api token
    global api_token_valid_start_epoch
    global api_token

    credentials = api_user + ":" + api_pw
    credentials_bytes = credentials.encode('ascii')
    base64_bytes = base64.b64encode(credentials_bytes)
    encoded_credentials = base64_bytes.decode('ascii')
    # api call details
    jss_token_url = jss + "/api/v1/auth/token"
    payload = {}

    headers = {
        'Authorization': 'Basic ' + encoded_credentials
    }

    response = requests.request("POST", jss_token_url, headers=headers, data=payload)
    check_response_code(str(response), jss_token_url)
    # parse the json from the request
    response_data_dict = json.loads(response.text)
    # assign variable as global to be used in other functions
    api_token = response_data_dict['token']
    # Token is valid for 30 minutes. Setting timestamp to check for renewal
    api_token_valid_start_epoch = int(time.time())

    return api_token


def check_token_expiration_time():
    """api_token_valid_start_epoch is created globally when token is generated and api_token_valid_check_epoch is created locally to generate
    api_token_valid_duration_seconds which determines how long the token has been active"""
    api_token_valid_check_epoch = int(time.time())
    api_token_valid_duration_seconds = api_token_valid_check_epoch - api_token_valid_start_epoch
    # Renew token if necessary
    if api_token_valid_duration_seconds >= 1500:
        write_to_logfile(
            f"UPDATE: API auth token is {api_token_valid_duration_seconds} seconds old. Token will now be renewed to continue API access.....",
            now_formatted, "std")
        generate_auth_token()


def check_response_code(response_code: str, api_call: str):
    response_code = str(response_code)
    response_code = response_code[11:14]
    if response_code != "200" and response_code != "201":
        write_to_logfile(f"ERROR: response returned for {api_call} [{response_code}]", now_formatted, "std")
        print(f"ERROR: response returned [{response_code}]")
        print(response_code)
        sys.exit(1)
    else:
        write_to_logfile(f"INFO: http response for {api_call} [{response_code}]", now_formatted, "debug")


def get_all_ids(device_type, filename):
    page_size = 1000
    page = 0

    def refresh_api_url():
        if device_type == 'computers':
            api_url = jss + f"/api/v1/computers-inventory?section=GENERAL&page={page}&page-size={page_size}&sort=id%3Aasc"
        elif device_type == 'mobiledevices':
            api_url = jss + f"/api/v2/mobile-devices?page={page}&page-size={page_size}&sort=id%3Aasc"
        return api_url

    api_url = refresh_api_url()

    payload = {}
    headers = {
        'Authorization': 'Bearer ' + api_token
    }

    check_token_expiration_time()
    response = requests.request("GET", api_url, headers=headers, data=payload)
    check_response_code(str(response), api_url)
    reply = response.text  # just the json, to save to file
    # write JSON to /tmp/jss_temp.....
    print(reply, file=open(json_path + filename, "w+", encoding='utf-8'))  # writes output to /tmp

    all_ids_json_filepath = open(json_path + filename, encoding='utf-8')
    all_ids_json_data = json.load(all_ids_json_filepath)

    total_id_count = all_ids_json_data['totalCount']
    write_to_logfile(f"INFO: {device_type} found in Jamfcloud [{total_id_count}]", now_formatted, "std")

    # loop through JSON results in order to create list of all IDs
    all_ids = []
    # append all IDs to variables established above
    count_on_page = page_size
    # adjust variable if total is less than page size. This avoids creating "list index out of range" error when looping through IDs
    if total_id_count < count_on_page:
        count_on_page = total_id_count

    id_index = 0
    while id_index < count_on_page:
        next_id = all_ids_json_data['results'][id_index]['id']
        all_ids.append(next_id)
        id_index += 1

    all_ids_count = len(all_ids)
    write_to_logfile(f"INFO: IDs retrieved [{all_ids_count} of {total_id_count}].....", now_formatted, "std")

    while all_ids_count < total_id_count:
        page += 1
        api_url = refresh_api_url()
        check_token_expiration_time()
        response = requests.request("GET", api_url, headers=headers, data=payload)
        check_response_code(str(response), api_url)
        reply = response.text
        # write JSON to /tmp/jss_temp.....
        print(reply, file=open(json_path + filename, "w+", encoding='utf-8'))

        all_ids_json_filepath = open(json_path + filename, encoding='utf-8')
        all_ids_json_data = json.load(all_ids_json_filepath)

        id_index = 0
        should_keep_tabulating = True
        while should_keep_tabulating:
            if all_ids_count < total_id_count and id_index < count_on_page:
                next_id = all_ids_json_data['results'][id_index]['id']
                all_ids.append(next_id)
                id_index += 1
                # refresh count of IDs
                all_ids_count = len(all_ids)
            else:
                should_keep_tabulating = False

        write_to_logfile(f"INFO: IDs retrieved [{all_ids_count} of {total_id_count}].....", now_formatted, "std")
    all_ids_json_filepath.close()
    os.remove(json_path + filename)
    if test_mode_tf:
        all_ids = all_ids[0]
        write_to_logfile(f"TEST MODE: enabled and stopping at first device object [id: {all_ids}]. JSON will display all apps without full device information.....", now_formatted, "std")
    return all_ids


def parse_mobile_device_info():
    # loop through the IDs we gathered in previous step
    for id in all_ids:
        write_to_logfile(f"INFO: parsing mobile device with id: {id}", now_formatted, "debug")
        # make api call to retrieve inventory for each computer
        # use subset/Applications to only return the list of applications by mobile device ID
        api_url = f"{jss}/JSSResource/mobiledevices/id/{id}/subset/Applications"
        tmp_file = f"{json_path}_mobileDeviceID_{id}.xml"
        payload = {}
        headers = {
            'Accept': 'application/xml',
            'Authorization': 'Bearer ' + api_token
        }

        check_token_expiration_time()
        response = requests.request("GET", api_url, headers=headers, data=payload)
        check_response_code(str(response), api_url)
        reply = response.text  # just the xml, to save to file
        # write XML to /tmp folder
        print(reply, file=open(tmp_file, "w+", encoding='utf-8'))
        # parse all computer info
        tree = ET.parse(tmp_file)
        root = tree.getroot()

        mobile_device_id = id
        # mobile_device_application_name = " "
        # mobile_device_application_short_version = " "
        # mobile_device_application_status = " "
        # mobile_device_identifier = " "
        for a in root.findall('.//application'):
            # mobile_device_application_name = getattr(a.find('application_name'), 'text', None)
            mobile_device_identifier = getattr(a.find('identifier'), 'text', None)
            mobile_device_application_status = getattr(a.find('application_status'), 'text', None)
            mobile_device_application_short_version = getattr(a.find('application_short_version'), 'text', None)
            # append values to JSON output files
            bundle_id_without_dots = mobile_device_identifier.replace(".", "-")
            filename = f"{tmp_path}{bundle_id_without_dots}.json"
            insert_into_json(filename, mobile_device_id, mobile_device_application_status, mobile_device_application_short_version)
        os.remove(tmp_file)


def gather_application_ids():
    # gather all application IDs and assign as key pairs with application name
    write_to_logfile(f"INFO: gathering all application IDs and names", now_formatted, "debug")
    # make api call to retrieve inventory for each computer
    # use subset/Applications to only return the list of applications by mobile device ID
    api_url = f"{jss}/JSSResource/mobiledeviceapplications"
    tmp_file = f"{json_path}allMobileDeviceApplications.json"
    payload = {}
    headers = {
        'Accept': 'application/json',
        'Authorization': 'Bearer ' + api_token
    }

    check_token_expiration_time()
    response = requests.request("GET", api_url, headers=headers, data=payload)
    check_response_code(str(response), api_url)
    reply = response.text  # just the xml, to save to file
    # write JSON to /tmp folder
    print(reply, file=open(tmp_file, "w+", encoding='utf-8'))
    # parse all mobile application info
    all_app_ids_json_filepath = open(tmp_file, encoding='utf-8')
    all_app_ids_json_data = json.load(all_app_ids_json_filepath)
    app_ids = []
    app_names = []
    app_display_names = []
    app_bundle_ids = []
    index = 0
    for element in all_app_ids_json_data['mobile_device_applications']:
        app_id = element["id"]
        app_name = element["name"]
        app_bundle_id = element["bundle_id"]

        write_apps_to_tmp_json(app_id, app_name, app_bundle_id)
        index += 1

    all_app_ids_json_filepath.close()
    os.remove(tmp_file)
    return app_ids, app_names, app_bundle_ids


def write_apps_to_tmp_json(app_id, app_name, app_bundle_id):
    bundle_id_without_dots = app_bundle_id.replace(".", "-")
    tmp_file = f"{tmp_path}{bundle_id_without_dots}.json"
    json_data = {
        "application_id": app_id,
        "application_name": app_name,
        "bundle_id": app_bundle_id,
        "devices": [
        ]
    }
    json_formatted_str = json.dumps(json_data, indent=4)
    print(json_formatted_str, file=open(tmp_file, "w+", encoding='utf-8'))  # writes output to /tmp


def insert_into_json(filename, mobile_device_id, mobile_device_application_status, mobile_device_application_short_version,):
    """Takes the parsed app and device info and inserts into temp JSON files then assemgles main JSON file"""

    # First checks if application is installed by Jamf (ex: has app ID) or installed by user (doesn't have app ID)
    file_exists = os.path.exists(filename)

    if file_exists:
        new_data = {"device_id": mobile_device_id,
                    "application_version": mobile_device_application_short_version,
                    "application_status": mobile_device_application_status
                    }

        with open(filename, 'r+', encoding='utf-8') as updated_file:
            # First we load existing data into a dict.
            file_data = json.load(updated_file)
            # Join new_data with file_data inside emp_details
            file_data["devices"].append(new_data)
            # Sets file's current position at offset.
            updated_file.seek(0)
            # convert back to json.
            json.dump(file_data, updated_file, indent=4)


def compile_json_files_write_to_main_output():
    filename = json_path + f"mobile_applications_{now_formatted}.json"
    write_to_logfile(f"UPDATE: mobile device parsing complete! Assembling JSON output file at [{filename}] ", now_formatted, "debug")
    json_data = {
        "mobile_device_applications": [
        ]
    }
    json_formatted_str = json.dumps(json_data, indent=4)
    print(json_formatted_str, file=open(filename, "w+", encoding='utf-8'))  # writes output to main script output folder

    # iterate over all json files in directory
    all_json = []
    for i in os.listdir(tmp_path):
        # read app-specific JSON into json_piece variable
        with open(tmp_path + i, 'r+', encoding='utf-8') as json_piece:
            all_json.append(json.load(json_piece))
            json_piece.close()

    # open newly-created json file and begin appending to it
    with open(filename, "r+", encoding='utf-8') as json_main:
        completed_json = json.load(json_main)
        completed_json["mobile_device_applications"].append(all_json)
        # Sets file's current position at offset.
        json_main.seek(0)
        json.dump(all_json, json_main)

    """The following is temporary until it is determined why the main tags do not persist when adding json_pieces """
    prepend = '{ "mobile_device_applications": '
    with open(filename, 'r+') as file:
        content = file.read()
        file.seek(0)
        file.write(prepend + content)

    append = '}'
    print(append, file=open(filename, "a+", encoding='utf-8'))
    """To here"""
    # delete all temporary app-info json files
    delete_tmp_json_files(False)


def write_to_logfile(log_to_print, timestamp, debug_or_std):
    # create file if it doesn't exist. the "w+ option overwrites existing file content.
    if debug_or_std == "std":
        print(log_to_print, file=open(log_folder_path + "/JamfAPISync-" + timestamp + ".log", "a+", encoding='utf-8'))
    elif debug_or_std == "debug" and debug_mode_tf:
        # only print debug logs if debug_mode_tf is true
        print(f"DEBUG: {log_to_print}", file=open(log_folder_path + "/JamfAPISync-" + timestamp + ".log", "a+", encoding='utf-8'))


def now_date_time():
    now = str(datetime.datetime.now())
    # splits string into a list with 2 entries
    now = now.split(".", 1)
    # assign index 0 of the new list (as a string) to now
    now_formatted = str(now[0])

    char_to_replace = {':': '', ' ': '-'}
    # Iterate over all key-value pairs in dictionary
    for key, value in char_to_replace.items():
        # Replace key character with value character in string
        now_formatted = now_formatted.replace(key, value)

    return now_formatted


def script_duration(start_or_stop):
    # this function calculates script duration
    days = 0; hours = 0; mins = 0; secs = 0
    global start_script_epoch

    if start_or_stop == "start":
        print("[SCRIPT START]")
        start_script_epoch = int(time.time())  # converting to int for simplicity
    else:
        stop_script_epoch = int(time.time())
        script_duration_in_seconds = stop_script_epoch - start_script_epoch

        if script_duration_in_seconds > 59:
            secs = int(script_duration_in_seconds % 60)
            script_duration_in_seconds = int(script_duration_in_seconds / 60)

            if script_duration_in_seconds > 59:
                mins = int(script_duration_in_seconds % 60)
                script_duration_in_seconds = script_duration_in_seconds / 60

                if script_duration_in_seconds > 23:
                    hours = int(script_duration_in_seconds % 24)
                    days = int(script_duration_in_seconds / 24)
                else:
                    hours = int(script_duration_in_seconds)
            else:
                mins = int(script_duration_in_seconds)
        else:
            secs = int(script_duration_in_seconds)

        write_to_logfile(f"\n\n\n---------------\nSUCCESS: script completed.  JSON file can be found in {json_path}", now_formatted, "std")
        write_to_logfile(f"SCRIPT DURATION: {days} day(s) {hours} hour(s) {mins} minute(s) {secs} second(s)", now_formatted,
                         "std")
        print("[SCRIPT COMPLETE!]")


def create_script_directory(days_ago_to_delete_logs):
    # Check whether the specified path exists or not
    path_exists_logs = os.path.exists(log_folder_path)
    path_exists_tmp = os.path.exists(tmp_path)

    if not path_exists_logs and not path_exists_tmp:
        # Create a new directory because it does not exist
        os.makedirs(log_folder_path)
        os.makedirs(tmp_path)
        write_to_logfile(f"CREATE: new directories created in [{json_path}]!", now_formatted, "debug")
    else:
        write_to_logfile(f"INFO: the script directories already exist. Check [{json_path}]", now_formatted, "debug")

        x_days_ago = time.time() - (days_ago_to_delete_logs * 86400)
        write_to_logfile(f"DELETE: deleting log files older than {days_ago_to_delete_logs} days", now_formatted, "debug")

        for i in os.listdir(log_folder_path):
            path = os.path.join(log_folder_path, i)

            if os.stat(path).st_mtime <= x_days_ago and os.path.isfile(path):
                os.remove(path)
                write_to_logfile(f"DELETE: [{path}]", now_formatted, "std")

        delete_tmp_json_files(True)


def delete_tmp_json_files(log_output):
    # deletes all .json files temporarily created for each application, named by bundle ID in ~/JamfAPISync/tmp
    tmp_files_deleted = 0
    for i in os.listdir(tmp_path):
        path = os.path.join(tmp_path, i)
        os.remove(path)
        tmp_files_deleted += 1

    if log_output:
        write_to_logfile(f"DELETE: deleting any temp files from last session", now_formatted, "std")
        write_to_logfile(f"DELETE: temp files deleted in {tmp_path} [{tmp_files_deleted}]", now_formatted, "std")


if __name__ == "__main__":
    script_duration("start")
    now_formatted = now_date_time()
    jss, api_user, api_pw, json_path, log_folder_path, tmp_path, debug_mode_tf, test_mode_tf = init_vars()
    create_script_directory(14)
    api_token = generate_auth_token()
    app_ids, app_names, app_bundle_ids = gather_application_ids()
    all_ids = get_all_ids("mobiledevices", "all_mobile_devices.json")
    parse_mobile_device_info()
    compile_json_files_write_to_main_output()
    script_duration("stop")
