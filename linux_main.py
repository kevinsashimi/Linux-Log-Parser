# Linux Log Parser Script for Linux

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
from time import sleep, perf_counter


def parse_args():
    parser = argparse.ArgumentParser(description="Parses Linux logs to ELK")
    parser.add_argument('-s', '--system', action='store', nargs=1, metavar='SYS', default=None, help="Specify type of OS")
    parser.add_argument('-u', '--url', action='store', nargs=1, metavar='HOST', default=None, help="Specify the URL for Elasticsearch instance (Including port number)")
    parser.add_argument('-i', '--index', action='store', nargs=1, metavar='INDEX', default=None, help="Specify the index on Elasticsearch")
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
            print("Configuration file found for " + system)
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

    # Check if data folder exists in filebeat folder
    not_found = True
    for dirs in os.listdir(filebeat_dir):
        if "data" in dirs:
            if os.path.isdir(data_path):
                print(f"Data path found: {data_path}")
                not_found = False
                break

    if not_found:
        try:
            print("Data path not found!")
            print(f"Creating new directory, \"data\" in {filebeat_dir}")
            os.makedirs(data_path, mode=664)

        except Exception as e:
            print(e)
            print(f"Unable to create the directory, \"data\" in {filebeat_dir}")
            print("Please check directory permissions")
            sys.exit(1)

    # Check if the folder that saves the state of the logs for the specified triage output exists
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


def build_cmd(abs_path, filebeat_dir, preset_cmd, config_file):
    total_expected_doc_count = 0
    module_list = []
    module_flag = "-modules="

    for module in config_file.keys():
        module_list.append(module)

    print("Modules found: " + str(module_list))

    # Append modules to command
    module_flag += ",".join([str(m) for m in module_list])
    preset_cmd.append(module_flag)

    module_dir = os.path.join(filebeat_dir, "modules.d")
    for module in module_list:
        not_found = True
        for module_d in os.listdir(module_dir):
            if module in module_d:  # Check if filebeat supports the module specified in the configuration file
                not_found = False
                print("Configuration file found: " + module_d)

                # Retrieve log type from specified module
                log_types_list = []
                for log_type in config_file[module].keys():
                    log_types_list.append(log_type)
                print("Log types found: " + str(log_types_list))

                # Retrieve file paths from each filetype
                for filetype in config_file[module].keys():
                    file_path_list = config_file[module][filetype]
                    all_files = grab_logs(abs_path, file_path_list)
                    print("Path list of log files found:")
                    pprint.pp(all_files)

                    expected_doc_count = 0
                    for file in all_files:
                        with open(file, 'r') as f:
                            count = len(f.readlines())

                        print(f"Total lines in {os.path.basename(file)}: {count}")
                        expected_doc_count += count

                    total_expected_doc_count += expected_doc_count

                    all_files = str(all_files)
                    system_path = f"{module}.{filetype}.var.paths={all_files}"
                    preset_cmd.append("-M")
                    preset_cmd.append(system_path)

        if not_found:
            print(f"The module, \"{module}\" cannot be found in {module_dir}")
            sys.exit(1)

    preset_cmd.append("--once")

    return preset_cmd, total_expected_doc_count


def grab_logs(abs_path, file_path_list):
    # Grab logs
    all_files = []
    for sub_path in file_path_list:
        print("Retrieving paths containing " + sub_path)
        full_filepath = os.path.join(abs_path, sub_path)
        full_sub_path, filename = os.path.split(full_filepath)
        full_filepath_list = find(filename, full_sub_path)

        if not full_filepath_list:
            print("No paths were found...")

        for filepath in full_filepath_list:
            all_files.append(filepath)

    return all_files


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


def format_time(t):
    if t >= 59 * 60:
        hours = int(t / 60 / 60)
        minutes = int((t - (hours * 60 * 60)) / 60)
        seconds = t - ((hours * 60 * 60) + (minutes * 60))
        return f"{hours}hr {minutes}min {seconds:0.2f}s"

    elif t >= 60:
        minutes = int(t / 60)
        seconds = t - (minutes * 60)
        return f"{minutes}min {seconds:0.2f}s"

    else:
        return f"{t:0.2f}s"


def main():
    # Parse arguments
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

    print("Number of triage outputs to upload: " + str(path_count))
    print("Path list of triage outputs:")
    pprint.pp(str(abs_path_list))
    exit()
    if args.url is None:
        print("Please specify the URL for Elastic Search instance (Including port number)")
        sys.exit(1)

    if args.index is None:
        print("Please specify the index on Elastic Search")
        sys.exit(1)

    not_found = True
    if args.path:
        filebeat_dir = args.path
        if os.path.isdir(filebeat_dir):
            print("Filebeat directory set to " + args.path)

        else:
            not_found = False

    else:
        for dirs in os.listdir("."):
            if "filebeat" and "linux" in dirs:
                default_path = os.path.join(".", dirs)
                if os.path.isdir(default_path):
                    filebeat_dir = default_path
                    not_found = False
                    break

    if not_found:
        print("Filebeat directory not found, please ensure that filebeat is downloaded in the current working directory or its specified directory path is relative to the current working directory.")
        print("Use the '-p' option if located in another folder")
        sys.exit(1)

    # Run filebeat for each triage output specified in the list
    for path in abs_path_list:
        # Translates to absolute path and check if directory exists
        abs_path = os.path.abspath(path)
        if not os.path.isdir(abs_path):
            print("The following indicated path cannot be found: " + abs_path)
            sys.exit(1)

        basename = os.path.basename(abs_path)
        fb_state_dir = check_registry_folder(filebeat_dir, basename)

        # Check and retrieve config file if specified OS exists
        config_file = check_system(system)
        print(f"Loading configuration file for {system}...")
        pprint.pp(config_file)

        preset_cmd = [
            filebeat_dir + '/filebeat',
            '-e',
            '-c', filebeat_dir + '/filebeat.yml',
            '-E', 'output.elasticsearch.hosts=[\"' + url + '\"]',
            '-E', 'output.elasticsearch.index=\'' + index_name + '\'',
            '-E', 'setup.template.name=\'' + index_name + '\'',
            '-E', 'setup.template.pattern=\'' + index_name + '\'',
            '-E', 'setup.ilm.enabled=false',
            '-E', 'filebeat.registry.path=\'' + fb_state_dir + '\''
        ]

        command, total_expected_doc_count = build_cmd(abs_path, filebeat_dir, preset_cmd, config_file)

        # Print the built command executed
        print_cmd = ''
        for cmd in command:
            print_cmd = print_cmd + " " + cmd
        print("Command executed:")
        print(print_cmd)

        # Connect to Elasticsearch
        es = connect_es(url)
        create_index(es, index_name)

        query = os.path.join(url, index_name, "_count").replace('\\', '/')
        curr_doc_count = requests.get(query).json()['count']

        # Parse the logs to filebeat
        print("Uploading logs from \"" + basename + "\" to filebeat...")
        start_time = perf_counter()

        try:
            subprocess.Popen(command).wait()

        except Exception as e:
            print(e)

        sleep(5)  # Allow some time for the logs to upload completely to filebeat
        stop_time = perf_counter() - start_time

        """
        It is recommended to check and refresh the total document count on Elasticsearch itself directly rather than the
        queried values at runtime of this script (the code below) as the logs may need some time to be uploaded
        and may not be an accurate representation of the final document count
        """
        post_doc_count = requests.get(query).json()['count']
        uploaded_doc_count = post_doc_count - curr_doc_count
        failed_doc_count = total_expected_doc_count - uploaded_doc_count

        print("Upload completed!")
        print(f"Total logs expected: {total_expected_doc_count}")
        print(f"Total logs uploaded: {uploaded_doc_count}")
        print(f"Total logs failed to upload: {failed_doc_count}")
        print(f"Total logs ingested in {index_name} on Elasticsearch: {post_doc_count}")
        print(f"Time elapsed: {format_time(stop_time)}")


if __name__ == '__main__':
    main()
