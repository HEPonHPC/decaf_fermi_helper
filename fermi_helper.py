#!/usr/bin/env python3
# vim: sta:et:sw=4:ts=4:sts=4
"""
NAME
    fermi_helper.py - Build and run Fermi HEP workflow using Docker/Singularity

SYNOPSIS
    python3 fermi_helper.py build-docker-image [--tag TAG]
        [--only-dependencies] [--pull-dependencies TAG] [--decaf-root ROOT]
        [--decaf-repo REPO] [--decaf-repo-branch BRANCH]
    python3 fermi_helper.py run-docker-image [--tag TAG] [--interactive]
    python3 fermi_helper.py build-singularity-image [--tag TAG] [--sif SIF]
    python3 fermi_helper.py run-singularity-image [--sif SIF] [--interactive]

EXAMPLE
    Install Python dependency to run this script
        $ python3 -m pip install --user jinja2

    Build the Docker image, using pre-built dependencies
        $ python3 fermi_helper.py build-docker-image --pull-dependencies thobson2/decaf-fermi:0.2.0-base

    Run the Docker image
        $ python3 fermi_helper.py run-docker-image

    Build the dependencies and push them to DockerHub
        $ python3 fermi_helper.py build-docker-image --only-dependencies --tag USERNAME/decaf-fermi:0.2.0-base

    Convert Docker image to Singularity image
        $ python3 fermi_helper.py build-singularity-image
    
    Run Singularity image
        $ python3 fermi_helper.py run-singularity-image

DESCRIPTION
    This script takes care of the build and execution process needed to run the
    Fermi workflow using Decaf within Linux containers.

    The build does everything within a container, which means that the entire
    build process happens inside of Docker, and the image is, in a sense,
    hermetically sealed away from the host system. The catch is that any change
    to source code requires a complete re-build of all of Decaf and the
    workflow, which can take up to 5 minutes.

    Either build process happens within Docker first and uses a Dockerfile to
    define the commands to be run. This Docker image can be used directly, or
    can be converted into a Singularity image and then run using Singularity.

    build-docker-image
        Copy the source code into Docker and build Decaf and the Fermi
        workflow.

    run-docker-image
        Run the workflow inside of Docker using the already-built Docker image.

    build-singularity-image
        Convert a Docker image into a Singularity image

    run-singularity-image
        Run the workflow inside of Singularity

OPTIONS
    --tag TAG
        Set the Docker image tag to be used. If named something like
        USERNAME/IMAGENAME:VERSION, then the image will be pushed to a Docker
        registry afterwards. Otherwise, a name like IMAGENAME:VERSION will only
        be saved locally.

    --sif SIF
        Set the path to the Singularity image to be used.

    --interactive
        Instead of immediately running the workflow, open a shell into the
        container to manually run the workflow and debug.

    --decaf-root ROOT
        Set the location of the decaf source code (including Fermi workflow).

    --decaf-repo REPO
        If the Decaf root directory doesn't exist, Decaf is first cloned using
        this repo url.

    --decaf-repo-branch BRANCH
        The branch to be checked out after cloning Decaf (see --decaf-repo).

    --only-dependencies
        Only build the dependencies inside of Docker, without compiled Decaf.

    --pull-dependencies TAG
        Instead of building the whole set of dependencies, use the pre-built
        image TAG.

FILES
    go.sh
        A helper script used in the Dockerfile to run CMake with the correct
        arguments.

    docker.env.sh
        A helper script that sets some variables to be used inside the go.sh
        script.

NOTES
    The build-docker-image and run-docker-image commands require Docker to be
    installed, but do not require Singularity installed. Likewise,
    build-singularity-image and run-singularity-image require Singularity, but
    not Docker. This means that those commands can be run on different machines
    (provided the image is pushed to a registry, c.f. --tag option above with a
    "/" separator)

BUGS
    Currently, even if Python source code is changed, the hermetic build and
    run process will rebuild everything, despite it being unnecessary for an
    interpreted script. This could be fixed in one of two ways: 1) copy only
    C++ source code first and then Python source code, or 2) build and run
    incrementally.

CHANGELOG
    v0.2.0, 01 October 2020
        Remove incremental building for now until it's been tested more. Right
        now, only hermetic builds are supported, though now the dependencies
        can be pre-built and saved to a Docker registry to be used. This needs
        templates to work effectively, hence the introduction of the jinja2
        library dependency.

    v0.1.0, 24 September 2020
        First release with full support for hermetic builds and in-progress
        support for incremental ones.

AUTHORS
    Tanner Hobson <thobson2@vols.utk.edu>

"""

from subprocess import run
from textwrap import dedent
from pathlib import Path

from jinja2 import Template


setupscript = dedent("""\
    #ls -lah /.singularity.d/
    . /etc/profile
    #cat /.singularity.d/runscript -A
    #set -euo pipefail
""")


hermeticscript = dedent("""\
    #ls -lah /.singularity.d/
    . /etc/profile
    #cat /.singularity.d/runscript -A
    set -euo pipefail
    DECAF_PREFIX=/opt/decaf/stage
    DECAF_HENSON_PREFIX=${DECAF_PREFIX:?}/examples/henson
    FERMI_PREFIX=${DECAF_PREFIX:?}/examples/fermi_hep
    cd "$(TMPDIR=/tmp mktemp -d)"
    tmpdir=$PWD

    cp -r "${DECAF_PREFIX:?}" "${tmpdir:?}"
    cd stage/examples/fermi_hep
    echo $PWD

    mkdir conf
    mv "${FERMI_PREFIX:?}/mb7tev.txt" conf/
    cp "${FERMI_PREFIX:?}/hep-fullWorkflow-inputPre.json" ./decaf-henson.json
    sed -ie 's!/home/oyildiz/decaf-henson/install!'"$tmpdir/stage"'!g' ./decaf-henson.json
    #sed -ie 's!\\./!'"${FERMI_PREFIX:?}/"'!g' ./decaf-henson.json
    #cp "${FERMI_PREFIX:?}/hostfile_workflow.txt" ./hostfile_workflow.txt
    cp "${DECAF_HENSON_PREFIX:?}/python/decaf-henson_python" ./decaf-henson_python

    LD_LIBRARY_PATH=${LD_LIBRARY_PATH:+${LD_LIBRARY_PATH:?}:}${DECAF_PREFIX:?three}/lib
    export DECAF_PREFIX LD_LIBRARY_PATH
""")


runscript = dedent("""\
    mpirun --hostfile hostfile_workflow.txt -np 4 ./decaf-henson_python
""")

intscript = dedent("""\
    exec bash
""")


dockerfile_template = Template(dedent("""\
    {% if not pull_dependencies %}
    # Build stage with Spack pre-installed and ready to be used
    FROM spack/ubuntu-bionic:latest as builder

    # What we want to install and how we want to install it
    # is specified in a manifest file (spack.yaml)
    RUN mkdir /opt/spack-environment \\
    &&  (echo "spack:" \\
    &&   echo "  view: /opt/view" \\
    &&   echo "  specs:" \\
    &&   echo "  - boost" \\
    &&   echo "  - cmake" \\
    &&   echo "  - henson +mpi-wrappers +python ^mpich@3.3.2 ^python@3.8.2" \\
    &&   echo "  - py-h5py ^hdf5@1.10.2 ^mpich@3.3.2 ^python@3.8.2" \\
    &&   echo "  - py-scipy@1.3.3 ^python@3.8.2" \\
    &&   echo "  - autoconf" \\
    &&   echo "  - automake" \\
    &&   echo "  - hepmc@2.06.10" \\
    &&   echo "  - diy@master ^mpich@3.3.2" \\
    &&   echo "  config:" \\
    &&   echo "    install_tree: /opt/software" \\
    &&   echo "  concretization: together") > /opt/spack-environment/spack.yaml

    # Install the software, remove unecessary deps
    RUN cd /opt/spack-environment && spack install && spack gc -y

    RUN cd /opt/spack-environment && spack add pythia8 && spack install && spack gc -y

    ## Strip all the binaries
    #RUN find -L /opt/view/* -type f -exec readlink -f '{}' \; | \\
    #    xargs file -i | \\
    #    grep 'charset=binary' | \\
    #    grep 'x-executable\|x-archive\|x-sharedlib' | \\
    #    awk -F: '{print $1}' | xargs strip -s

    # Modifications to the environment that are necessary to run
    RUN cd /opt/spack-environment && \\
        spack env activate --sh -d . >> /etc/profile.d/z10_spack_environment.sh


    # Bare OS image to run the installed executables
    FROM ubuntu:18.04 AS dependencies

    RUN apt-get update && \\
        apt-get install -y \\
            build-essential \\
            wget \\
            gfortran \\
        && \\
        rm -rf /var/lib/apt/lists/*

    COPY --from=builder /opt/spack-environment /opt/spack-environment
    COPY --from=builder /opt/software /opt/software
    COPY --from=builder /opt/view /opt/view
    COPY --from=builder /etc/profile.d/z10_spack_environment.sh /etc/profile.d/z10_spack_environment.sh

    ADD apprentice-latest-nodata.tar.gz /opt
    RUN . /etc/profile && \\
        python3.8 -m ensurepip && \\
        python3.8 -m pip install virtualenv && \\
        python3.8 -m virtualenv /opt/venv && \\
        /opt/venv/bin/python -m pip install \\
            networkx \\
            cython \\
            /opt/apprentice-latest \\
        && \\
        echo '. /opt/venv/bin/activate' > /etc/profile.d/z15_python_environment.sh

    RUN . /etc/profile && \\
        mkdir /opt/rivet && \\
        cd /opt/rivet && \\
        wget https://phab.hepforge.org/source/rivetbootstraphg/browse/3.0.2/rivet-bootstrap?view=raw -O rivet-bootstrap && \\
        chmod +x rivet-bootstrap && \\
        { RIVET_VERSION=2.7.2 YODA_VERSION=1.7.5 HEPMC_VERSION=2.06.09 FASTJET_VERSION=3.3.2 ./rivet-bootstrap || true; } && \\
        rm YODA-1.7.5/pyext/yoda/util.cpp && \\
        RIVET_VERSION=2.7.2 YODA_VERSION=1.7.5 HEPMC_VERSION=2.06.09 FASTJET_VERSION=3.3.2 ./rivet-bootstrap && \\
        echo '. /opt/rivet/local/rivetenv.sh' > /etc/profile.d/z20_rivet_environment.sh

    {% endif %}

    {% if pull_dependencies %}
    FROM {{ pull_dependencies }} AS dependencies
    {% endif %}


    FROM dependencies AS final

    {% if not only_dependencies %}

    SHELL ["/bin/bash", "--rcfile", "/etc/profile", "-l", "-c"]
    WORKDIR /opt
    COPY {{ decaf_root }} /opt/decaf
    WORKDIR /opt/decaf
    COPY go.sh docker.env.sh /opt/decaf/
    RUN sed -ie '/extern "C" void \*(\*dlsym(void \*handle, const char \*symbol))();/d' /opt/view/include/Pythia8/PythiaStdlib.h && \\
        rm -rf /opt/view/include/diy/thirdparty/fmt && \\
        cp -r include/fmt /opt/view/include/diy/thirdparty/fmt

    RUN . /etc/profile && \\
        . /opt/venv/bin/activate && \\
        ENV=docker ./go.sh cmake && \\
        ENV=docker ./go.sh make

    {% endif %}

    ENTRYPOINT ["/bin/bash", "--rcfile", "/etc/profile"]
    CMD ["-l"]
"""))


def _make_script(interactive: bool) -> str:
    script = setupscript
    script += hermeticscript

    if interactive:
        script += intscript
    else:
        script += runscript

    return script


def main_build_docker_image(decaf_root, decaf_repo, decaf_repo_branch, tag, only_dependencies, pull_dependencies):
    if not decaf_root.exists():
        run(
            ['git', 'clone', str(decaf_repo), str(decaf_root)],
            check=True,
        )

        run(
            ['git', 'checkout', str(decaf_repo_branch)],
            cwd=decaf_root,
        )

    dockerfile = dockerfile_template.render(
        decaf_root=decaf_root.relative_to(Path.cwd()),
        only_dependencies=only_dependencies,
        pull_dependencies=pull_dependencies,
    ).encode('utf-8')

    if only_dependencies:
        target = 'dependencies'
    else:
        target = 'final'

    run(
        ['docker', 'build', '-t', str(tag), '-f', '-', '--target', str(target), '.'],
        input=dockerfile,
        check=True,
    )

    if '/' in tag:
        run(
            ['docker', 'push', str(tag)],
            check=True,
        )


def main_run_docker_image(tag, interactive):
    script = _make_script(interactive)

    run(
        ['docker', 'run', '-it', '--rm', str(tag), '--rcfile', '/etc/profile', '-c', script, 'decaf-fermi-wrapper'],
        check=True,
    )


def main_build_singularity_image(tag, sif):
    if '/' in tag:
        tag = 'docker://{}'.format(tag)
    else:
        tag = 'docker-daemon://{}'.format(tag)

    run(
        ['singularity', 'build', str(sif), str(tag)],
        check=True,
    )


def main_run_singularity_image(interactive):
    script = _make_script(interactive)

    run(
        ['singularity', 'exec', './decaf-fermi.sif', 'bash', '--rcfile', '/etc/profile', '-c', script, 'decaf-fermi-wrapper'],
        check=True,
    )


def cli():
    def wrap_exception(func):
        def inner(s):
            try:
                return func(s)
            except Exception as e:
                raise argparse.ArgumentTypeError(str(e))

        return inner

    @wrap_exception
    def tag(s):
        assert sum(1 for c in s if c == '/') <= 1, 'Expected 0 or 1 "/" separator in tag (user/imagename or imagename)'
        assert ':' in s, 'Expected ":" separator in tag (version, e.g. "latest")'
        return s

    @wrap_exception
    def sif(s):
        path = Path(s)
        path = path.resolve(strict=False)  # new in Python3.6+
        assert path.suffix == '.sif', 'Expected sif extension'
        assert path.parent.exists(), 'Expected parent directory to exist: {}'.format(path.parent)
        return path

    import argparse

    parser = argparse.ArgumentParser()
    parser.set_defaults(main=None)
    subparsers = parser.add_subparsers()

    subparser = subparsers.add_parser('build-docker-image')
    subparser.set_defaults(main=main_build_docker_image)
    subparser.add_argument('--decaf-root', type=Path, default=Path.cwd() / 'decaf')
    subparser.add_argument('--decaf-repo', default='git@bitbucket.org:tpeterka1/decaf.git')
    subparser.add_argument('--decaf-repo-branch', default='decaf-henson')
    subparser.add_argument('--tag', default='decaf-fermi:latest', type=tag,
                           help='e.g. MyUsername/MyImage:latest or my.registry.example.com:5000/MyUsername/MyImage:latest')
    subparser.add_argument('--only-dependencies', action='store_true')
    subparser.add_argument('--pull-dependencies', type=tag)

    subparser = subparsers.add_parser('run-docker-image')
    subparser.set_defaults(main=main_run_docker_image)
    subparser.add_argument('--tag', default='decaf-fermi:latest', type=tag,
                           help='e.g. MyUsername/MyImage:latest or my.registry.example.com:5000/MyUsername/MyImage:latest')
    subparser.add_argument('--interactive', action='store_true')

    subparser = subparsers.add_parser('build-singularity-image')
    subparser.set_defaults(main=main_build_singularity_image)
    subparser.add_argument('--tag', '-t', default='decaf-fermi:latest', type=tag,
                           help='e.g. MyUsername/MyImage:latest or my.registry.example.com:5000/MyUsername/MyImage:latest')
    subparser.add_argument('--sif', '-s', default=sif('./decaf-fermi.sif'), type=sif,
                           help='e.g. path/to/image.sif')

    subparser = subparsers.add_parser('run-singularity-image')
    subparser.set_defaults(main=main_run_singularity_image)
    subparser.add_argument('--sif', default=sif('./decaf-fermi.sif'), type=sif,
                           help='e.g. path/to/image.sif')
    subparser.add_argument('--interactive', action='store_true')

    args = vars(parser.parse_args())
    main = args.pop('main')

    if main is None:
        parser.print_usage()
        return

    main(**args)


if __name__ == '__main__':
    cli()
