FROM ghcr.io/osgeo/gdal:ubuntu-small-3.7.0

ENV LANG="C.UTF-8" LC_ALL="C.UTF-8"
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y software-properties-common

RUN apt-get update && \
    apt-get -qq install -y --no-install-recommends g++ && \
    apt-get -qq install -y --no-install-recommends python3-pip && \
    apt-get -qq install -y --no-install-recommends python3-dev && \
    apt-get -qq install -y --no-install-recommends python3-venv && \
    rm -rf /var/lib/apt/lists/*

RUN curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip" && \
    unzip awscliv2.zip && \
    ./aws/install

WORKDIR /home/fit_changedetector

COPY requirements*.txt ./

RUN python3 -m venv /opt/venv && \
    /opt/venv/bin/python -m pip install -U pip && \
    /opt/venv/bin/python -m pip install --no-cache-dir --upgrade numpy && \
    /opt/venv/bin/python -m pip install --no-cache-dir -r requirements.txt

ENV PATH="/opt/venv/bin:$PATH"