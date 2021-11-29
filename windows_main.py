# Linux Log Parser Script for Windows

import argparse
import os
import sys
import yaml
import gzip
import shutil
import pprint
import subprocess
import requests
from elasticsearch import Elasticsearch
from time import sleep


HOST = "http://chr-elk01.chr.lab:9200"


def parse_args():
    parser = argparse.ArgumentParser(description="Parses Linux logs to ELK")
    parser.add_argument('-s', '--system', action='store', nargs=1, metavar='SYS', default=None, help="Specify type of OS")
    parser.add_argument('-u', '--url', action='store', nargs=1, metavar='HOST', default=None, help="Specify the URL for Elastic Search instance (Including port number)")
    parser.add_argument('-i', '--index', action='store', nargs=1, metavar='INDEX', default=None, help="Specify the index on Elastic Search")
    parser.add_argument('-p', '--path', action='store', nargs='?', metavar='PATH', default=False, help="Specify the path for Filebeat directory")
    parser.add_argument('dir', action='store', nargs=argparse.REMAINDER, metavar='DIR', default=None, help="Specify directory path to extract and parse logs from")

    # Print help message if no arguments were passed
    if len(sys.argv) == 1:
        parser.print_help(sys.stderr)
        sys.exit(1)

    return parser.parse_args()


def check_system(system):
    for c_file in os.listdir("./config"):
        # Supports .yml extension
        if c_file[:-4] == system and c_file[-4:] == ".yml":
            return read_yaml(c_file)

    print(f"{system} is currently not supported or configuration file not found")
    sys.exit(1)


def read_yaml(c_file):
    try:
        conf_file_path = os.path.join("./config", c_file)
        with open(conf_file_path, "r") as yml_file:
            config_file = yaml.safe_load(yml_file)
            return config_file

    except Exception as e:
        print(e)
        print(f"The configuration file, \"{c_file}\" cannot be found! Please check if the file exists")
        sys.exit(1)


def find(file_search, path):
    filtered = []
    result = []
    for root, dirs, files in os.walk(path):
        for name in files:
            if file_search in name:
                filtered.append(os.path.join(root, name))

    # Check for zip files
    for file in filtered:
        if ".gz" in file:
            new_filename = file[:-3]
            if new_filename in result:
                print(new_filename + " exists in results. Skipping...")
                continue

            with gzip.open(file, 'rb') as f_in:
                with open(new_filename, 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)

            result.append(new_filename)

        else:
            if file in result:
                print(file + " exists in results. Skipping...")
                continue
            result.append(file)

    return result


def check_registry_folder(filebeat_dir, basename):
    data_path = os.path.join(filebeat_dir, "data")
    base_path = os.path.join(data_path, basename)

    for dirs in os.listdir(data_path):
        if basename in dirs:
            if os.path.isdir(base_path):
                try:
                    print(f"The directory, \"{basename}\" already exists in {data_path}, removing...")
                    shutil.rmtree(base_path)

                except Exception as e:
                    print(e)
                    print("The directory, \"" + basename + "\" cannot be deleted. Please check if the directory is in use")
                    sys.exit(1)

                break

    try:
        print(f"Creating new directory, \"{basename}\" in {data_path}")
        os.makedirs(base_path, mode=664)

    except Exception as e:
        print(e)
        print(f"Unable to create the directory, \"{basename}\" in {data_path}")
        print("Please check directory permissions")
        sys.exit(1)

    return os.path.join(".", basename)


def connect_es(host):
    try:
        es = Elasticsearch([host], timeout=60)

    except Exception as e:
        print("Connection failed, please check if specified URL is valid")
        print(f"Error: {e}")
        sys.exit(1)

    print("Connection established")
    return es


def create_index(es, index_name):
    print(f"Creating index: {index_name}")
    setting = {
        "settings": {
            "index.mapping.total_fields.limit": 100000,
            # "index.mapping.ignore_malformed": "true",
        }
    }

    try:
        if es.indices.exists(index=index_name):
            print("Index already exists, proceeding to upload logs...")

        else:
            response = es.indices.create(index=index_name, body=setting, ignore=400)

            if 'acknowledged' in response:
                if response['acknowledged']:
                    print("Index Mapping success for index: "+response['index'])
                    return True

            # catch API error response
            elif 'error' in response:
                print("ERROR:"+str(response['error']['root_cause']))
                print("TYPE:"+str(response['error']['type']))

    except Exception as e:
        print(f"Connection error: {e}")


def main():
    args = parse_args()
    system = args.system[0]
    url = args.url[0]
    index_name = args.index[0]
    filebeat_dir = ''

    if args.system is None:
        print("Please specify the operating system.")
        sys.exit(1)

    if not args.dir:
        print("Please specify the file path.")
        sys.exit(1)

    abs_path_list = []
    path_count = len(args.dir)  # Number of triage outputs to upload
    for relative_path in args.dir:
        if os.path.exists(relative_path):
            abs_path = os.path.abspath(relative_path)
            if not os.path.isdir(abs_path):
                print("The following indicated path cannot be found: " + abs_path)
                sys.exit(1)

            else:
                abs_path_list.append(abs_path)

        else:
            print("The following indicated path cannot be found: " + relative_path)
            sys.exit(1)

    pprint.pp("Path list: " + str(abs_path_list))

    # **************************************************************************<-----Loop each folder in args.dir here
    # Translates to absolute path and check if directory exists
    abs_path = os.path.abspath(args.dir[0])  # Temporary code to use args.dir[0] as a single file for now
    if not os.path.isdir(abs_path):
        print("The following indicated path cannot be found: " + abs_path)
        sys.exit(1)

    if args.url is None:
        print("Please specify the URL for Elastic Search instance (Including port number)")
        sys.exit(1)

    if args.index is None:
        print("Please specify the index on Elastic Search")
        sys.exit(1)

    if args.path:
        print("Filebeat directory set to " + args.path)
        filebeat_dir = args.path

    else:
        not_found = True
        for dirs in os.listdir("."):
            if "filebeat" in dirs:
                default_path = os.path.join(".", dirs)
                if os.path.isdir(default_path):
                    filebeat_dir = default_path
                    not_found = False
                    break

        if not_found:
            print("Filebeat directory not found, please ensure that filebeat is downloaded in the current directory or specify its directory path (use -p option) if located in another folder")
            sys.exit(1)

    basename = os.path.basename(abs_path)
    fb_state_dir = check_registry_folder(filebeat_dir, basename)

    print(f"Loading configuration file for {system}...")
    # Check and retrieve config file if specified OS exists
    config_file = check_system(system)
    print("Keys loaded:")
    for key in config_file.keys():  # <-------------------- Loop here to run filebeat for each key value in config file
        print(key)

    config_file_path = config_file['system']  # <---------------Temporary code to extract system file paths

    # Prints the list of directories in given file path
    # for filename in os.listdir(args.dir[0]):
    #     print(filename)

    # Grab logs
    all_files = []
    for sub_path in config_file_path:
        print(sub_path)
        full_filepath = os.path.join(abs_path, sub_path)
        full_sub_path, filename = os.path.split(full_filepath)
        for filepath in find(filename, full_sub_path):
            all_files.append(filepath)

    print("Log files found:")
    pprint.pp(all_files)

    # Count total number of documents expected
    expected_doc_count = 0
    for file in all_files:
        with open(file, 'r') as f:
            count = len(f.readlines())

        print(f"Total lines in {os.path.basename(file)}: {count}")
        expected_doc_count += count

    print(f"Total document count: {expected_doc_count}")

    es = connect_es(url)
    create_index(es, index_name)

    query = os.path.join(url, index_name, "_count").replace('\\', '/')
    curr_doc_count = requests.get(query).json()['count']

    # Parse the logs to filebeat
    print("Sending logs to filebeat...")
    all_files = str(all_files)

    try:
        # fb_inputs = "filebeat.inputs=[{type:log, enabled:true, paths:" + all_files + ", close_inactive:3s, close_removed:true, clean_removed:true}]"
        fb_inputs = "filebeat.inputs=[{type:log, enabled:true, paths:" + "['C:\\Users\\User\\Downloads\\Ensign\\Projects\\Linux-Log-Parser\\References\\centos7-triage_20211006_143423\\var\\log\\syslog*']" + ", close_inactive:3s, close_removed:true, clean_removed:true}]"
        # fb_state_dir = "C:\\Users\\User\\Downloads\\Ensign\\Projects\\Linux-Log-Parser"

        # process = subprocess.Popen([filebeat_dir + '\\filebeat.exe',
        #                             '-e',
        #                             '-c', filebeat_dir + '\\filebeat.yml',
        #                             '-E', 'output.elasticsearch.hosts=[\"' + url + '\"]',
        #                             '-E', 'output.elasticsearch.index=\'' + index_name + '\'',
        #                             '-E', 'setup.template.name=\'' + index_name + '\'',
        #                             '-E', 'setup.template.pattern=\'' + index_name + '\'',
        #                             '-E', 'setup.ilm.enabled=false',
        #                             '-E', fb_inputs,
        #                             '-E', 'filebeat.registry.path=\'' + fb_state_dir + '\'',
        #                             '--once']).wait()

        path1 = "system.syslog.var.paths=['./References/ubuntu-triage_20211110_062835/var/log/syslog*']"
        path2 = "system.syslog.var.paths=['./References/ubuntu-triage_20211110_062835/var/log/auth.log*']"
        system_path = "filebeat.config.modules=[{module:system, enabled:true, syslog:{enabled:true, var.paths:['C:\\Users\\User\\Downloads\\Ensign\\Projects\\Linux-Log-Parser\\References\\centos7-triage_20211006_143423\\var\\log\\syslog*']}}]"
        process = subprocess.Popen([filebeat_dir + '\\filebeat.exe',
                                    '-e',
                                    '-c', filebeat_dir + '\\filebeat.yml',
                                    '-E', 'output.elasticsearch.hosts=[\"' + url + '\"]',
                                    '-E', 'output.elasticsearch.index=\'' + index_name + '\'',
                                    '-E', 'setup.template.name=\'' + index_name + '\'',
                                    '-E', 'setup.template.pattern=\'' + index_name + '\'',
                                    '-E', 'setup.ilm.enabled=false',
                                    '-E', 'filebeat.registry.path=\'' + fb_state_dir + '\'',
                                    '-E', fb_inputs,
                                    '-E', system_path,
                                    '--once']).wait()

        # Remove the .wait() from the variable process to see the executed raw command as it will cause a deadlock
        # cmd = ''
        # for x in range(len(process.args)):
        #     cmd = cmd + " " + process.args[x]
        # print("Command executed:" + cmd)
        # print(process.stderr.read().decode('utf-8'))
        # print(process.stdout.read().decode('utf-8'))

    except Exception as e:
        print(e)

    sleep(5)  # Allow some time for the logs to upload completely to filebeat
    """
    It is recommended to check and refresh the total document count on filebeat itself directly rather than the
    queried values at runtime of this script (the code below) as the logs may need some time to be uploaded
    and may not be an accurate representation of the final document count
    """
    post_doc_count = requests.get(query).json()['count']
    uploaded_doc_count = post_doc_count - curr_doc_count
    failed_doc_count = expected_doc_count - uploaded_doc_count

    print("Upload completed!")
    print(f"Total logs uploaded: {uploaded_doc_count}")
    print(f"Total logs failed to upload: {failed_doc_count}")
    print(f"Total logs on filebeat: {post_doc_count}")


if __name__ == '__main__':
    main()
    # Command Lines for testing:
    # python windows_main.py -s rhel7 -d C:\Users\User\Downloads\Ensign\Projects\Linux-Log-Parser\References\centos7-triage_20211006_143423 -u http://chr-elk01.chr.lab:9200 -i linux_log_parser_win
    # python windows_main.py -s rhel7 -u http://chr-elk01.chr.lab:9200 -i linux_log_parser_win .\References\centos7-triage_20211006_143423 .\References\ubuntu-triage_20211110_062835
    # curl -X GET "http://chr-elk01.chr.lab:9200/linux_log_parser_win/_count?pretty"
    # 8hVVVnYue9ansVg
    # DNS: 10.11.10.11
