#!/bin/sh

# Check HOST_ENV for determining Apache settings
if [ "$HOST_ENV" = "production" ]; then
    # Set Apache to hide server details for production
    sed -i 's/^#ServerTokens Prod/ServerTokens Prod/' /usr/local/apache2/conf/httpd.conf
    sed -i 's/^#ServerSignature Off/ServerSignature Off/' /usr/local/apache2/conf/httpd.conf
    echo "Production mode enabled"
else
    # Set Apache to display full server details for development
    sed -i 's/^ServerTokens Prod/#ServerTokens Prod/' /usr/local/apache2/conf/httpd.conf
    sed -i 's/^ServerSignature Off/#ServerSignature Off/' /usr/local/apache2/conf/httpd.conf
    echo "Development mode enabled"
fi

exec "$@"
