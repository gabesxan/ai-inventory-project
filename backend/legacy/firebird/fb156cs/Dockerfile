FROM i386/debian:stretch
RUN printf 'deb http://archive.debian.org/debian stretch main\n' > /etc/apt/sources.list \
 && apt-get -o Acquire::Check-Valid-Until=false update \
 && apt-get install -y --no-install-recommends libstdc++5 libncurses5 file procps openssl \
 && rm -rf /var/lib/apt/lists/*
COPY FirebirdCS-1.5.6.5026-0.i686.tar.gz /tmp/
RUN cd /tmp && tar xzf FirebirdCS-1.5.6.5026-0.i686.tar.gz \
 && tar xzf FirebirdCS-1.5.6.5026-0.i686/buildroot.tar.gz -C / \
 && rm -rf /tmp/Firebird* \
 && ls /opt/firebird/bin
# Replace the default SYSDBA password with a random one readable only by root in the guest.
RUN P=$(openssl rand -hex 4) \
 && /opt/firebird/bin/gsec -user SYSDBA -password masterkey -modify SYSDBA -pw "$P" \
 && printf 'ISC_USER=SYSDBA\nISC_PASSWORD=%s\n' "$P" > /opt/firebird/SYSDBA.password \
 && chmod 600 /opt/firebird/SYSDBA.password
ENV FIREBIRD=/opt/firebird PATH=/opt/firebird/bin:$PATH LD_LIBRARY_PATH=/opt/firebird/lib
