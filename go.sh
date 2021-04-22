#!/usr/bin/env bash

die() { printf $'Error: %s\n' "$*" >&2; exit 1; }

root=$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)
decaf=${root:?}/decaf
build=${decaf:?}/build
stage=${decaf:?}/stage
rivet=${decaf:?}/rivet
version=${version:-v0.2.7}
tag=${tag:-decaf:${version:?}-fermi_hep}


ENV=${root:?}/${ENV:+${ENV}.}env.sh
[ -f "$ENV" ] && . "$ENV"

go-exec() {
    local opt_workdir opt OPTARG OPTIND
    opt_workdir=
    while getopts "w:" opt; do
        case "$opt" in
        (w) opt_workdir=$OPTARG;;
        esac
    done
    shift $((OPTIND-1))

    if [ -n "$opt_workdir" ]; then
        cd "$opt_workdir" || die "Could not chdir to '$opt_workdir'"
    fi

    export LD_LIBRARY_PATH=${LD_LIBRARY_PATH:+${LD_LIBRARY_PATH:?}:}/opt/view/lib
    exec "$@"
}

go-docker() {
    go-docker-"$@"
}

go-docker-build() {
    exec docker build \
        -t ${tag:?} \
        "$@" \
        ${root:?}
}

go-docker-run() {
    exec docker run \
        -it \
        --rm \
        --mount type=bind,src=${root:?},dst=${root:?} \
        --workdir ${root:?} \
        --env ENV=docker \
        ${tag:?} \
        ${root:?}/go.sh \
            "$@"
}

go-decaf() {
    go-decaf-"$@"
}

go-decaf-exec() {
    export LD_LIBRARY_PATH=${LD_LIBRARY_PATH:+${LD_LIBRARY_PATH:?}:}${stage:?}/lib
    go-exec "$@"
}

go-decaf-cmake() { 
    venv=${VIRTUAL_ENV:?not in a virtualenv}
    spackenv=/opt/view
    henson=${spackenv:?}
    libhenson=${henson:?}/lib/libhenson.a
    pythia8=${spackenv:?}
    libpythia8=${pythia8:?}/lib/libpythia8.so 

    [ -d "${henson:?}" ] || die "henson doesn't exist: $henson"
    [ -f "${libhenson:?}" ] || die "libhenson doesn't exist: $libhenson"
    [ -f "${libpythia8:?}" ] || die "libpythia8 doesn't exist: $libpythia8" 

    exec cmake -H"${decaf:?}" -B"${build:?}" \
        -DCMAKE_INSTALL_PREFIX:PATH="${stage:?}" \
        -DHENSON_LIBRARY="${libhenson:?}" \
        -DHENSON_INCLUDE_DIR:PATH="${henson:?}" \
        -DPYTHIA8_DIR:PATH="${pythia8:?}" \
        -DCMAKE_CXX_COMPILER=mpicxx \
        -DCMAKE_C_COMPILER=gcc \
        -DRIVET_DIR:PATH=${rivet:?} \
        -DFASTJET_DIR:PATH=${rivet:?} \
        -DYODA_DIR:PATH=${rivet:?} \
        -DHEPMC_DIR:PATH=${rivet:?} \
        -Duse_boost=OFF
} 

go-decaf-make() {
    exec make -C "${build:?}" \
        VERBOSE=1 \
        "$@"
} 

go-"$@"
