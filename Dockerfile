# Build stage with Spack pre-installed and ready to be used
FROM spack/ubuntu-bionic:latest as builder

# What we want to install and how we want to install it
# is specified in a manifest file (spack.yaml)
RUN mkdir /opt/spack-environment \
&&  (echo "spack:" \
&&   echo "  view: /opt/view" \
&&   echo "  specs:" \
&&   echo "  - boost" \
&&   echo "  - cmake" \
&&   echo "  - henson +mpi-wrappers +python ^mpich@3.3.2 ^python@3.8.2" \
&&   echo "  - py-h5py ^hdf5@1.10.2+hl ^mpich@3.3.2 ^python@3.8.2" \
&&   echo "  - py-scipy@1.3.3 ^python@3.8.2" \
&&   echo "  - autoconf" \
&&   echo "  - automake" \
&&   echo "  - hepmc@2.06.10" \
&&   echo "  - diy@master ^mpich@3.3.2" \
&&   echo "  config:" \
&&   echo "    install_tree: /opt/software" \
&&   echo "  concretization: together") > /opt/spack-environment/spack.yaml

# Install the software, remove unecessary deps
RUN cd /opt/spack-environment && spack --env . install && spack gc -y

RUN cd /opt/spack-environment && spack --env . add pythia8 && spack --env . install && spack gc -y

# Modifications to the environment that are necessary to run
RUN cd /opt/spack-environment && \
    spack env activate --sh -d . >> /etc/profile.d/z10_spack_environment.sh


# Bare OS image to run the installed executables
FROM ubuntu:18.04 AS dependencies

RUN apt-get update && \
    apt-get install -y \
        build-essential \
        wget \
        gfortran \
        git \
        zlib1g-dev \
    && \
    rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/spack-environment /opt/spack-environment
COPY --from=builder /opt/software /opt/software
COPY --from=builder /opt/view /opt/view
COPY --from=builder /etc/profile.d/z10_spack_environment.sh /etc/profile.d/z10_spack_environment.sh

RUN . /etc/profile && \
    python3.8 -m ensurepip && \
    python3.8 -m pip install virtualenv && \
    python3.8 -m virtualenv /opt/venv && \
    /opt/venv/bin/python -m pip install \
        pandas \
        networkx \
        cython \
        git+https://github.com/HEPonHPC/apprentice.git@6fbf531c4cb6537ef6323e150b854541b0ce961d \
    && \
    echo '. /opt/venv/bin/activate' > /etc/profile.d/z15_python_environment.sh

RUN . /etc/profile && \
    mkdir /opt/rivet && \
    cd /opt/rivet && \
    wget https://phab.hepforge.org/source/rivetbootstraphg/browse/3.0.2/rivet-bootstrap?view=raw -O rivet-bootstrap && \
    chmod +x rivet-bootstrap && \
    { RIVET_VERSION=2.7.2 YODA_VERSION=1.7.5 HEPMC_VERSION=2.06.09 FASTJET_VERSION=3.3.2 ./rivet-bootstrap || true; } && \
    rm YODA-1.7.5/pyext/yoda/util.cpp && \
    RIVET_VERSION=2.7.2 YODA_VERSION=1.7.5 HEPMC_VERSION=2.06.09 FASTJET_VERSION=3.3.2 ./rivet-bootstrap && \
    echo '. /opt/rivet/local/rivetenv.sh' > /etc/profile.d/z20_rivet_environment.sh

WORKDIR /tmp/fmt
COPY decaf/include/fmt /tmp/fmt
RUN sed -ie '/extern "C" void \*(\*dlsym(void \*handle, const char \*symbol))();/d' /opt/view/include/Pythia8/PythiaStdlib.h && \
    rm -rf /opt/view/include/diy/thirdparty/fmt && \
    mv /tmp/fmt /opt/view/include/diy/thirdparty/fmt

WORKDIR /opt

ENTRYPOINT ["/bin/bash", "--rcfile", "/etc/profile"]
CMD ["-l"]
