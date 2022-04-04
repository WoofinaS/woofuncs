import subprocess
import os
import traceback
from argparse import ArgumentParser
from queue import Queue
from threading import Thread
from time import perf_counter

## Thanks to BluABK for cleaning up the file a bit and to LordKitsuna for helping me keep my sanity


## About
## A simple script for encoding images to the next generation avif image format


## Dependency's
## aomenc-psy
## ffmpeg
## ffprobe
## MP4Box
## photon_noise_table dev tool renamed to photonnoise (Optional)


## TODO
## Detect if AOMENC-PSY is installed and disable features if its not
## Add suppot for more input formats
## Better handeling of passing thread affinity and disabiling it


NUM_THREADS = 4
CONFIG = '--enable-dual-filter=0 --deltaq-mode=3 --enable-chroma-deltaq=1 --tune=image_perceptual_quality ' \
         '--tune-content=default --dist-metric=qm-psnr --aq-mode=1 --enable-qm=1 --sharpness=1  --quant-b-adapt=1 ' \
         '--disable-trellis-quant=0 '


def main():
    args = get_args()
    check_args(args)

    if os.path.isfile(args.i):
        convert([0], args.i, args.o, args.q, args.p, args.b, args.n)
        if args.d == 1:
            os.remove(args.i)
    else:
        batch(args)


def get_args():
    parser = ArgumentParser()
    parser.add_argument('-i', metavar='', type=str, required=True, help='Input file/Directory')
    parser.add_argument('-o', metavar='', type=str, required=False, default='lol',
                        help='Output file (Only works with single file inputs)')
    parser.add_argument('-q', metavar='', type=int, required=False, default=16,
                        help='Quality to encode at (1 lossless - 63 Very Lossy) (Default: 16')
    parser.add_argument('-p', metavar='', type=int, required=False, default=3,
                        help='Sets the preset to encode at (0 Slowest - 9 Fastest) (Default: 3)')
    parser.add_argument('-b', metavar='', type=int, required=False, default=10,
                        help='Bitdepth to encode at (8, 10, 12) (Default: 10)')
    parser.add_argument('-d', metavar='', type=int, required=False, default=1,
                        help='Delete source file after converting (Default: 1)')
    parser.add_argument('-n', metavar='', type=int, required=False, default=320,
                        help='Noise level for photon table (default: 320)')

    return parser.parse_args()


def check_args(args):
    if not is_in_range(args.q, 1, 63):
        raise Exception('Invalid quality level "{}"'.format(args.q))
    if not is_in_range(args.p, 0, 9):
        raise Exception('Invalid preset level "{}"'.format(args.p))
    if args.b not in [8, 10, 12]:
        raise Exception('Invalid preset level "{}"'.format(args.b))
    if os.path.isfile(args.i):
        if filetype(args.o) != 'avif':
            raise Exception('Output Must be avif')
    elif not (os.path.isdir(args.i)):
        raise Exception('Invalid Input')
    try:
        run('photonnoise -h', [0])
    except:
        print('"photon_noise_table" devtool not detected, disabling grain synthesis.')
        args.n = 0


def batch(args):
    files = get_files(args.i)
    print('{} File(s) found'.format(len(files)))
    q = Queue()
    for f in files:
        q.put(f)
    for i in range(NUM_THREADS):
        Thread(target=task, daemon=True, args=([i], q, args)).start()

    q.join()


def task(thread_affinity: list, q, args):
    while q.qsize() > 0:
        start = perf_counter()
        in_file = q.get()
        try:
            convert(thread_affinity, in_file, change_filetype(in_file, 'avif'), args.q, args.p, args.b, args.n)
            if args.d == 1:
                os.remove(in_file)
        except Exception as e_inner:
            # Print entire traceback.
            print(traceback.format_exc())
            # Print exception line.
            print(e_inner)
        else:
            print('Finished "{in_file}" in {sec} second(s)'.format(
                in_file=true_file_name(in_file), sec=round(perf_counter() - start, 2)))

        q.task_done()


def get_files(dir_name):
    files_to_process = []
    for root, subdirs, files in os.walk(dir_name):
        for f in files:
            if filetype(f) in ['png', 'jpg', 'jpeg', 'jfif', 'webp']:
                files_to_process.append(os.path.join(root, f))

    return files_to_process


def convert(thread_affinity: list, in_file: str, out_file: str,
            quality: int, preset: int, bitdepth: int, iso: int):
    temp_ivf = change_filetype(in_file, 'ivf')
    temp_tbl = change_filetype(in_file, 'tbl')
    command = 'ffmpeg -loglevel panic -i "{in_file}" -strict -2 -pix_fmt {pixfmt} -f yuv4mpegpipe - | ' \
              'aomenc - -o "{temp_ivf}" --allintra --passes=1 --threads=1 --cpu-used={preset} --end-usage=q ' \
              '--cq-level={quality} '.format(in_file=in_file, pixfmt=pixfmt(bitdepth), temp_ivf=temp_ivf,
                preset=preset, quality=quality)
    if iso > 0:
        gen_tbl(thread_affinity, in_file, temp_tbl, iso)
        command += ' --enable-dnl-denoising=0 --film-grain-table="{temp_tbl}" '.format(temp_tbl=temp_tbl)
    command += CONFIG
    run(command, thread_affinity)
    run(f'MP4Box -add-image "{temp_ivf}":primary -ab avif -ab miaf -new "{out_file}"', thread_affinity)
    os.remove(temp_ivf)
    if iso > 0:
        os.remove(temp_tbl)


def gen_tbl(thread_affinity: list, in_file: str, out_file: str, iso: int):
    res = get_res(thread_affinity, in_file)
    run('photonnoise -w {w} -l {l} -i {iso} -b 25 -r 25 -o "{out_file}"'.format(w=res[0],
                                                                                l=res[1],
                                                                                iso=iso,
                                                                                out_file=out_file))


def get_res(thread_affinity: list, in_file: str):
    res = run('ffprobe -v error -select_streams v:0 -show_entries stream=width,height -of csv=p=0 "{in_file}"'.format(
        in_file=in_file), thread_affinity)

    return res.split('\n')[0].split(',')


def run(commands: str, thread_affinity=None):
    if thread_affinity is None:
        thread_affinity = [0]
    p = subprocess.Popen(args=commands, shell=True, stderr=subprocess.PIPE, stdout=subprocess.PIPE)
    try:
        os.sched_setaffinity(p.pid, thread_affinity)
    except:
        pass
    p.wait()
    if p.returncode != 0:
        raise Exception('Subprocces returned with non 0 return code ({})\n{}'.format(p.returncode,
                                                                                     p.communicate()[1].decode("utf8")))
    return p.communicate()[0].decode("utf8")


def is_in_range(val: int, min_val: float, max_val: float):
    return val >= min_val or max_val >= val


def change_filetype(in_file: str, file_extension: str):
    file_name_full = in_file.split('.')
    # Last element in list is the file extension part.
    file_name_full[-1] = file_extension

    return '.'.join(file_name_full)


def true_file_name(in_file: str):
    return in_file.split('/')[-1].lower()


def filetype(in_file: str):
    return in_file.split('.')[-1].lower()


def pixfmt(bitdepth: int):
    return ('yuv444p', 'yuv444p10le', 'yuv444p12le')[int((bitdepth - 8) / 2)]


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        # Print entire traceback.
        print(traceback.format_exc())
        # Print exception line.
        print(e)
    exit()
