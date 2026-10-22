FROM postgres:16-alpine3.24@sha256:721873c34ceb9f8d8fc265984940dc982404c105f19ad51be9fdc5970a6080ea

# The official image bundles gosu 1.19 with Go stdlib advisories. The entrypoint
# only invokes it as `gosu postgres ...`; use Alpine's small su-exec instead.
RUN apk add --no-cache su-exec \
    && rm /usr/local/bin/gosu
COPY gosu.sh /usr/local/bin/gosu
RUN chmod 0755 /usr/local/bin/gosu
