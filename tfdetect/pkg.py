#!/usr/bin/env python
import logging
import os
import re
import subprocess

from setuptools import find_packages, setup

from tfdetect import utils
from tfdetect.cuda import CUDA_LIBS, CURA_LIBS_MAP

log = logging.getLogger(__name__)

TRUTHY_STRINGS = ['true', 'True', 't', '1']

FORCE_GPU_ENV = 'TENSORFLOW_FORCE_GPU'

LDCONFIG_P_EXEC = ['ldconfig', '-Np']
LDCONFIG_P_RE = re.compile(
    r'^\t(?P<basename>[^\s]+) \((?P<archs>[^\)]+)\) => (?P<path>[^\s]+)$'
)


def get_version(fn='VERSION'):
    with open(fn, 'r') as fh:
        version = fh.readlines()[0].rstrip('\n')
    return version


def get_tf_version(version=get_version):
    if callable(version):
        version = version()

    tf_version = version.rsplit('+', 1)[0]
    return tf_version


def _iter_installed_libs(cmd=LDCONFIG_P_EXEC, cmd_line_re=LDCONFIG_P_RE):
    raw = subprocess.check_output(cmd)
    lines = raw.splitlines()

    for line in lines[1:]:
        line = utils.ensure_decoded_text(line)
        line = line.rstrip('\n')

        m = cmd_line_re.match(line)
        if not m:
            log.warning(
                'Could not parse %r output line: %r',
                LDCONFIG_P_EXEC,
                line,
            )
            continue

        yield m.groupdict()


_LIBS = list(_iter_installed_libs())


def _search_for_installed_lib(
        library_name,
        library_version=None,
        libs=_LIBS,
):
    log.info('Searching for library %r==%r', library_name, library_version)

    for lib in libs:
        base = lib['basename']

        found = []

        found.append(base.startswith(library_name))

        if library_version is not None:
            found.append(base.endswith('.%s' % library_version))

        found = all(found)

        if found:
            yield lib


def _get_cuda_libs_for_tf_version(tf_version):
    for prefix, libs in CURA_LIBS_MAP.items():
        if tf_version.startswith(prefix):
            return libs


def _has_libs(libs):
    log.info('Looking for libraries %r', libs)

    ret = True

    for lib_name, lib_version in libs.items():
        found = list(_search_for_installed_lib(lib_name, lib_version))
        log.info(
            'Found library %r: %r', '%s==%s' % (lib_name, lib_version), found
        )
        if not found:
            log.warning(
                'Could not find library %r', '%s==%s' % (lib_name, lib_version)
            )
            ret = False

    return ret


def detect_tensorflow_package(tf_version=get_tf_version):
    if callable(tf_version):
        tf_version = tf_version()

    log.info(
        'Detecting whether we should require tensorflow gpu or cpu variant.'
    )

    use_gpu = {}

    force_gpu = os.environ.get(FORCE_GPU_ENV)
    force_gpu = force_gpu in TRUTHY_STRINGS
    use_gpu.update(force_gpu=force_gpu)

    libs = _get_cuda_libs_for_tf_version(tf_version)
    log.info('CUDA libs for tf_version=%s' % tf_version)

    has_libs = False
    if libs:
        has_libs = _has_libs(libs)
    use_gpu.update(has_libs=has_libs)

    do_use_gpu = any(use_gpu.values())
    log.info('Tensorflow detection results: use_gpu=%r do_use_gpu=%r', use_gpu, do_use_gpu)

    if do_use_gpu:
        log.warning(
            'Detected CUDA installation; requiring GPU tensorflow variant.',
        )
    else:
        log.warning(
            'Did NOT detect CUDA installation; requiring CPU tensorflow variant.',
        )

    suffix = do_use_gpu and '-gpu' or ''
    name = 'tensorflow%s==%s' % (suffix, tf_version)

    return name
