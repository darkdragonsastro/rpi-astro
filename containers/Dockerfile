ARG SUITE=bookworm
FROM debian:${SUITE}
COPY scripts/bootstrap.sh /usr/local/bin/rpi-astro-bootstrap
RUN bash /usr/local/bin/rpi-astro-bootstrap
ENV DEBIAN_FRONTEND=noninteractive
WORKDIR /workspace
