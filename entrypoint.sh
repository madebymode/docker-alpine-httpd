#!/bin/bash

# Enable specified Apache modules
if [ -n "$APACHE_MODULES" ]; then
    IFS=',' read -ra MODULES <<< "$APACHE_MODULES"
    for module_info in "${MODULES[@]}"; do
        IFS=' ' read -ra module_parts <<< "$module_info"
        module_name=${module_parts[0]}
        module_path=${module_parts[1]}
        sed -i "s/^#LoadModule ${module_name} ${module_path}/LoadModule ${module_name} ${module_path}/" /usr/local/apache2/conf/httpd.conf
        echo "Enabled module at ${module_path}"
    done
fi

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
