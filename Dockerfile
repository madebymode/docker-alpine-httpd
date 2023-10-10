ARG PLATFORM="amd64"

ARG ALPINE_VERSION=${ALPINE_VERSION}
ARG APACHE_VERSION=${APACHE_VERSION}

# Use the Alpine-based Apache HTTP Server image
FROM --platform=$PLATFORM httpd:${APACHE_VERSION}-alpine${ALPINE_VERSION}

LABEL maintainer="madebymode"

# default values to connect to php-fpm
ENV PHP_HOST php
ENV PHP_PORT 9000

# Add your custom configuration files
ADD php-fpm.conf /usr/local/apache2/conf/extra/
# Copy entrypoint script
COPY entrypoint.sh /usr/local/bin/entrypoint

# Update and install latest packages and prerequisites
RUN apk update && apk upgrade && apk add --update --no-cache shared-mime-info bash \
    && rm -rf /var/cache/apk/* \
    && sed -i 's/^#LoadModule proxy_module modules\/mod_proxy.so/LoadModule proxy_module modules\/mod_proxy.so/' /usr/local/apache2/conf/httpd.conf \
    && sed -i 's/^#LoadModule proxy_fcgi_module modules\/mod_proxy_fcgi.so/LoadModule proxy_fcgi_module modules\/mod_proxy_fcgi.so/' /usr/local/apache2/conf/httpd.conf \
    && sed -i 's/^#LoadModule rewrite_module modules\/mod_rewrite.so/LoadModule rewrite_module modules\/mod_rewrite.so/' /usr/local/apache2/conf/httpd.conf \
    && sed -i '$aIncludeOptional conf/vhosts/*.conf' /usr/local/apache2/conf/httpd.conf \
    && sed -i '$aInclude conf/extra/php-fpm.conf' /usr/local/apache2/conf/httpd.conf \
    && mkdir -p /usr/local/apache2/conf/vhosts

EXPOSE 80
EXPOSE 443



# Set permissions for the entrypoint script
RUN chmod +x /usr/local/bin/entrypoint

# Set entrypoint
ENTRYPOINT ["entrypoint"]
# Set default command
CMD ["httpd-foreground"]
