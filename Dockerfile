FROM python:3.8.3-slim-buster AS base

# Dedicated Workdir for App
WORKDIR /pyrobomogen

# Do not run as root
RUN useradd -m -r pyrobomogen && \
    chown pyrobomogen /pyrobomogen

COPY requirements.txt /pyrobomogen
# RUN pip3 install -r requirements.txt

FROM base AS src
COPY . /pyrobomogen

# install pyrobomogen here as a python package
RUN pip3 install .

# USER pyrobomogen is commented to fix the bug related to permission
# USER pyrobomogen

COPY scripts/docker-entrypoint.sh /entrypoint.sh

# Use the `robot-generator` binary as Application
FROM src AS prod

# this is add to fix the bug related to permission
RUN chmod +x /entrypoint.sh

ENTRYPOINT [ "/entrypoint.sh" ]

CMD ["robot-generator", "-c", "config.yaml"]