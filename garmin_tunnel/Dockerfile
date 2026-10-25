FROM alpine:3.22
RUN apk add --no-cache ca-certificates curl unzip jq
RUN curl -fL \
https://github.com/openai/tunnel-client/releases/download/v0.0.18/tunnel-client-v0.0.18-linux-arm64.zip \
   -o /tmp/tunnel-client.zip \
&& mkdir -p /tmp/tunnel-client \
&& unzip -q /tmp/tunnel-client.zip -d /tmp/tunnel-client \
&& install -m 755 "$(find /tmp/tunnel-client -type f -name tunnel-client | head -n 1)" /usr/local/bin/tunnel-client \
&& rm -r /tmp/tunnel-client /tmp/tunnel-client.zip
COPY run.sh /run.sh
RUN chmod +x /run.sh
CMD ["/run.sh"]
