FROM python:3.8.3-slim-buster AS base

# Dedicated Workdir for App
WORKDIR /pyrobomogen

# Do not run as root
RUN useradd -m -r pyrobomogen && \
    chown user /pyrobomogen

COPY requirements.txt /pyrobomogen
RUN pip3 install -r requirements.txt

FROM base AS src
COPY . /pyrobomogen

USER pyrobomogen

FROM src AS prod
ENTRYPOINT [ "python3" ]
CMD ["main.py", "-c", "config.yaml"]