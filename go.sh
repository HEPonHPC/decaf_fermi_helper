#!/usr/bin/env bash

die() { printf $'Error: %s\n' "$*" >&2; exit 1; }

root=$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)
build=${root:?}/build
stage=${root:?}/stage
ext=${root:?}/ext
rivet=${ext:?}/rivet 

ENV=${root:?}/${ENV:+${ENV}.}env.sh
[ -f "$ENV" ] && . "$ENV"

go-cmake() { 
        venv=${VIRTUAL_ENV:?not in a virtualenv}
        spackenv=/opt/view
        henson=${spackenv:?}
        libhenson=${henson:?}/lib/libhenson.a
        pythia8=${spackenv:?}
        libpythia8=${pythia8:?}/lib/libpythia8.so 

        [ -d "${henson:?}" ] || die "henson doesn't exist: $henson"
        [ -f "${libhenson:?}" ] || die "libhenson doesn't exist: $libhenson"
        [ -f "${libpythia8:?}" ] || die "libpythia8 doesn't exist: $libpythia8" 

        cmake -H"${root:?}" -B"${build:?}" \
                -DCMAKE_INSTALL_PREFIX:PATH="${stage:?}" \
                -DHENSON_LIBRARY="${libhenson:?}" \
                -DHENSON_INCLUDE_DIR:PATH="${henson:?}" \
                -DPYTHIA8_DIR:PATH="${pythia8:?}" \
                -DCMAKE_CXX_COMPILER=mpicxx \
                -DCMAKE_C_COMPILER=gcc \
                -DRIVET_DIR:PATH=/opt/rivet/local \
                -DFASTJET_DIR:PATH=/opt/rivet/local \
                -DYODA_DIR:PATH=/opt/rivet/local \
                -DHEPMC_DIR:PATH=/opt/rivet/local \
                -Duse_boost=OFF
} 

go-make() {
        make -C "${build:?}" \
                VERBOSE=1 \
                "$@" \
        && \
        make -C "${build:?}" \
                install
} 

go-"$@"
