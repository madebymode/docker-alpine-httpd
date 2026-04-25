#!/bin/bash

set -e

runtime_dir="${HTTPD_RUNTIME_DIR:-/tmp/httpd-runtime}"
runtime_conf_dir="${HTTPD_RUNTIME_CONF_DIR:-/tmp/httpd-conf.d}"

mkdir -p "$runtime_dir" "$runtime_conf_dir"

cat > "${runtime_conf_dir}/00-runtime-state.conf" <<EOF
PidFile "${runtime_dir}/httpd.pid"
Mutex file:${runtime_dir}
EOF

cat > "${runtime_conf_dir}/10-environment.conf" <<EOF
ServerTokens Prod
ServerSignature Off
EOF

if [ "$HOST_ENV" != "production" ]; then
    cat > "${runtime_conf_dir}/10-environment.conf" <<EOF
ServerTokens Full
ServerSignature On
EOF
    echo "Development mode enabled"
else
    echo "Production mode enabled"
fi

cat > "${runtime_conf_dir}/20-modules.conf" <<EOF
# Generated at container startup.
EOF

if [ -n "$APACHE_MODULES" ]; then
    IFS=',' read -ra MODULES <<< "$APACHE_MODULES"
    for module_info in "${MODULES[@]}"; do
        module_info="${module_info#"${module_info%%[![:space:]]*}"}"
        module_info="${module_info%"${module_info##*[![:space:]]}"}"

        if [ -z "$module_info" ]; then
            continue
        fi

        IFS=' ' read -ra module_parts <<< "$module_info"
        module_name=${module_parts[0]}
        module_path=${module_parts[1]}

        if [ -z "$module_name" ] || [ -z "$module_path" ]; then
            echo "Skipping malformed APACHE_MODULES entry: ${module_info}" >&2
            continue
        fi

        printf 'LoadModule %s %s\n' "$module_name" "$module_path" >> "${runtime_conf_dir}/20-modules.conf"
        echo "Enabled module at ${module_path}"
    done
fi

echo "Initialized runtime config into ${runtime_conf_dir}"
