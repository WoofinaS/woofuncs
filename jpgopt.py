import subprocess
import os
from argparse import ArgumentParser
from queue import Queue
from threading import Thread
from time import perf_counter


## About
## A fancy Script for optimizing jpgs


def main():
    args = get_args()
    if (not os.path.isdir(args.i)):
        raise Exception('Input must be a directory')
    else:
        batch(args)


def get_args():
    parser = ArgumentParser()
    parser.add_argument('-i', metavar='', type=str, required=True, help='Input Directory')

    return parser.parse_args()


def batch(args):
    files = get_files(args.i)
    print('{} File(s) found'.format(len(files)))
    q = Queue()
    for f in files:
        q.put(f)
    for i in range(int(os.cpu_count()/2)):
        Thread(target=task, daemon=True, args=(q,)).start()
    q.join()


def task(q):
    while q.qsize() > 0:
        start = perf_counter()
        in_file = q.get()
        try:
            optimize(in_file)
        except Exception as e:
            print(e)
        else:
            print(f'Finished "{true_file_name(in_file)}" in ' \
                  f'{round(perf_counter() - start, 2)} second(s)')
        q.task_done()


def optimize(in_file: str):
    commands = f'jpegtran -outfile "{in_file}" "{in_file}"'
    p = subprocess.run(args=commands, shell=True, capture_output=True, text=True)
    if p.returncode != 0:
        raise Exception(f'jpegtran returned with non 0 return code ({p.returncode})\n{p}')


def get_files(dir_name):
    files_to_process = []
    for root, subdirs, files in os.walk(dir_name):
        for f in files:
            if filetype(f) in ['jpg', 'jpeg', 'jfif']:
                files_to_process.append(os.path.join(root, f))

    return files_to_process


def true_file_name(in_file: str):
    return in_file.split('/')[-1].lower()


def filetype(in_file: str):
    return in_file.split('.')[-1].lower()


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(e)