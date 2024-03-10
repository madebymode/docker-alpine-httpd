ARG ALPINE_VERSION=${ALPINE_VERSION}
ARG APACHE_VERSION=${APACHE_VERSION}

# Use TARGETPLATFORM in FROM line
FROM --platform=$TARGETPLATFORM httpd:${APACHE_VERSION}-alpine${ALPINE_VERSION}

# Redefine the ARGs after FROM (removing PLATFORM)
ARG APACHE_VERSION
ARG ALPINE_VERSION

LABEL maintainer="madebymode"
ENV PHP_HOST php
ENV PHP_PORT 9000

ADD php-fpm.conf /usr/local/apache2/conf/extra/
ADD server-status.conf /usr/local/apache2/conf/extra/

COPY entrypoint.sh /usr/local/bin/entrypoint

# Update, Upgrade, and install required packages
RUN apk update && apk upgrade && apk add --update --no-cache shared-mime-info bash curl su-exec shadow \
    && rm -rf /var/cache/apk/* \
    && sed -i 's/^#LoadModule status_module modules\/mod_status.so/LoadModule status_module modules\/mod_status.so/' /usr/local/apache2/conf/httpd.conf \
    && sed -i 's/^#LoadModule proxy_module modules\/mod_proxy.so/LoadModule proxy_module modules\/mod_proxy.so/' /usr/local/apache2/conf/httpd.conf \
    && sed -i 's/^#LoadModule proxy_fcgi_module modules\/mod_proxy_fcgi.so/LoadModule proxy_fcgi_module modules\/mod_proxy_fcgi.so/' /usr/local/apache2/conf/httpd.conf \
    && sed -i 's/^#LoadModule rewrite_module modules\/mod_rewrite.so/LoadModule rewrite_module modules\/mod_rewrite.so/' /usr/local/apache2/conf/httpd.conf \
    && sed -i 's/^#LoadModule deflate_module modules\/mod_deflate.so/LoadModule deflate_module modules\/mod_deflate.so/' /usr/local/apache2/conf/httpd.conf \
    && sed -i 's/^#LoadModule expires_module modules\/mod_expires.so/LoadModule expires_module modules\/mod_expires.so/' /usr/local/apache2/conf/httpd.conf \
    && sed -i 's/^#Include conf\/extra\/httpd-default.conf/Include conf\/extra\/httpd-default.conf/' /usr/local/apache2/conf/httpd.conf \
    && sed -i '$aIncludeOptional conf/vhosts/*.conf' /usr/local/apache2/conf/httpd.conf \
    && sed -i '$aInclude conf/extra/php-fpm.conf' /usr/local/apache2/conf/httpd.conf \
    && sed -i '$aInclude conf/extra/server-status.conf' /usr/local/apache2/conf/httpd.conf \
    && sed -i '$aServerName localhost' /usr/local/apache2/conf/httpd.conf \
    && mkdir -p /usr/local/apache2/conf/vhosts

EXPOSE 80
EXPOSE 443

# Health check using the Apache server-status page
HEALTHCHECK --interval=5s --timeout=1s --start-period=1s --retries=3 \
    CMD curl --header "Host: healthcheck.localhost" --fail http://localhost/server-status || exit 1

RUN chmod +x /usr/local/bin/entrypoint
ENTRYPOINT ["entrypoint"]
CMD ["httpd-foreground"]
