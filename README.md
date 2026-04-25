
# Alpine Apache Docker Image with Custom Entrypoint

This Docker image provides an Apache server with an optional PHP-FPM backend. It allows for dynamic enabling of Apache modules and adjusts server settings based on environment variables.


## Docker Hub

You can find our builds here:

https://hub.docker.com/r/mxmd/httpd/tags

ie:

```bash
docker pull mxmd/httpd:2.4
```



## Building the Docker Image Locally

First, make sure you've cloned the repository and you are inside the directory containing the Dockerfile:

```bash
docker build -t mxmd/httpd:2.4.66 .
```

The Dockerfile defaults currently target Apache `2.4.66` on Alpine `3.23`. You can still override them when needed:

```bash
docker build \
  --build-arg APACHE_VERSION=2.4.66 \
  --build-arg ALPINE_VERSION=3.23 \
  -t mxmd/httpd:2.4.66 .
```

## Running the Docker Image

You can run the image using:

```bash
docker run -d -p 80:80 -p 443:443 mxmd/httpd:2.4.66
```

### Hardened Tags

The default `mxmd/httpd` tags keep the original startup behavior and may modify Apache config files in place during container startup.

For read-only filesystem support, use the hardened tags instead:

- `mxmd/httpd:2.4.66-hardened`
- `mxmd/httpd:2.4-hardened`

Build the hardened image locally with the default versions:

```bash
docker build -f Dockerfile.hardened -t mxmd/httpd:2.4.66-hardened .
```

Or override the base versions explicitly:

```bash
docker build \
  --build-arg APACHE_VERSION=2.4.66 \
  --build-arg ALPINE_VERSION=3.23 \
  -f Dockerfile.hardened \
  -t mxmd/httpd:2.4.66-hardened .
```

### Running Hardened Tags with a Read-Only Filesystem

The hardened image supports `--read-only` by generating runtime Apache overrides into `HTTPD_RUNTIME_CONF_DIR` and writing pid or mutex state into `HTTPD_RUNTIME_DIR`.

By default those paths are:

- `HTTPD_RUNTIME_CONF_DIR=/tmp/httpd-conf.d`
- `HTTPD_RUNTIME_DIR=/tmp/httpd-runtime`

When using `--read-only`, mount `/tmp` as writable:

```bash
docker run -d \
  --read-only \
  --tmpfs /tmp \
  -p 80:80 \
  -p 443:443 \
  mxmd/httpd:2.4.66-hardened
```

Docker Compose example:

```yaml
services:
  httpd:
    image: mxmd/httpd:2.4.66-hardened
    read_only: true
    tmpfs:
      - /tmp
    ports:
      - "80:80"
      - "443:443"
```

If you want the generated config and runtime state to persist across restarts, mount a Docker volume instead:

```bash
docker volume create httpd-tmp

docker run -d \
  --read-only \
  -v httpd-tmp:/tmp \
  -p 80:80 \
  -p 443:443 \
  mxmd/httpd:2.4.66-hardened
```

### Provision Runtime Config Into a Volume

If you want a stricter split between config generation and the Apache listener, you can provision the runtime files into a Docker volume first and then run the hardened container in consume-only mode.

Create a volume:

```bash
docker volume create httpd-runtime
```

Populate it with the runtime config:

```bash
docker run --rm \
  -e HOST_ENV=production \
  -e APACHE_MODULES="ratelimit_module modules/mod_ratelimit.so" \
  -e HTTPD_RUNTIME_DIR=/runtime/state \
  -e HTTPD_RUNTIME_CONF_DIR=/runtime/conf \
  -v httpd-runtime:/runtime \
  mxmd/httpd:2.4.66-hardened \
  init-httpd
```

Then start Apache using the provisioned files:

```bash
docker run -d \
  --read-only \
  -e HTTPD_SKIP_GENERATION=1 \
  -e HTTPD_RUNTIME_DIR=/runtime/state \
  -e HTTPD_RUNTIME_CONF_DIR=/runtime/conf \
  -v httpd-runtime:/runtime \
  -p 80:80 \
  -p 443:443 \
  mxmd/httpd:2.4.66-hardened
```

Docker Compose example:

```yaml
services:
  init-httpd:
    image: mxmd/httpd:2.4.66-hardened
    command: ["init-httpd"]
    environment:
      HOST_ENV: production
      APACHE_MODULES: ratelimit_module modules/mod_ratelimit.so
      HTTPD_RUNTIME_DIR: /runtime/state
      HTTPD_RUNTIME_CONF_DIR: /runtime/conf
    volumes:
      - httpd-runtime:/runtime

  httpd:
    image: mxmd/httpd:2.4.66-hardened
    read_only: true
    depends_on:
      init-httpd:
        condition: service_completed_successfully
    environment:
      HTTPD_SKIP_GENERATION: "1"
      HTTPD_RUNTIME_DIR: /runtime/state
      HTTPD_RUNTIME_CONF_DIR: /runtime/conf
    volumes:
      - httpd-runtime:/runtime
    ports:
      - "80:80"
      - "443:443"

volumes:
  httpd-runtime:
```

If your Compose version does not support `condition: service_completed_successfully`, run `init-httpd` once before starting `httpd`:

```bash
docker compose run --rm init-httpd
docker compose up -d httpd
```

When `HTTPD_SKIP_GENERATION=1`, the container will fail fast if the required runtime files are missing from the mounted volume.

## Custom Entrypoint Features

### 1. Default Enabled Apache Modules

The following Apache modules come enabled by default:

- **core_module (static)**: Fundamental module for the operation of the Apache server.
- **so_module (static)**: Enables the loading of dynamic modules.
- **http_module (static)**: Core module for processing HTTP requests.
- **mpm_event_module (shared)**: Multi-Processing Module designed for high performance sites.
- **authn_file_module (shared)**: Provides file-based authentication.
- **authn_core_module (shared)**: Core authentication module.
- **authz_host_module (shared)**: Provides host-based authorization.
- **authz_groupfile_module (shared)**: Group file-based authorization.
- **authz_user_module (shared)**: User-based authorization.
- **authz_core_module (shared)**: Core authorization framework.
- **access_compat_module (shared)**: Provides access control compatibility.
- **auth_basic_module (shared)**: Basic authentication.
- **reqtimeout_module (shared)**: Sets timeout for reading request headers and body.
- **filter_module (shared)**: Content filter framework.
- **deflate_module (shared)**: Handles compression of content before it is delivered to the client.
- **mime_module (shared)**: Maps file extensions to MIME types.
- **log_config_module (shared)**: Provides flexible logging capabilities.
- **env_module (shared)**: Provides environment variable manipulation.
- **expires_module (shared)**: Enables control over the setting of Expires and Cache-Control HTTP headers.
- **headers_module (shared)**: Provides directives to manipulate HTTP response headers.
- **setenvif_module (shared)**: Allows conditional setting of environment variables.
- **version_module (shared)**: Determines the configuration layout version.
- **proxy_module (shared)**: Provides basic proxy capabilities.
- **proxy_fcgi_module (shared)**: Enables support for FastCGI proxy.
- **unixd_module (shared)**: UNIX daemon-related functionality.
- **status_module (shared)**: Provides server status information.
- **autoindex_module (shared)**: Generates directory listings.
- **dir_module (shared)**: Handles directory index files.
- **alias_module (shared)**: Provides mapping of URLs to file system locations.
- **rewrite_module (shared)**: Provides URL manipulation capabilities.

### 2. Dynamic Apache Modules Loading

You can enable additional Apache modules at runtime by passing the `APACHE_MODULES` environment variable. This variable should contain comma-separated values of the module's name and its path.

For example, to enable the `ratelimit_module` and `allowmethods_module`:

```bash
docker run -d -p 80:80 -p 443:443 -e APACHE_MODULES="ratelimit_module modules/mod_ratelimit.so,allowmethods_module modules/mod_allowmethods.so" mxmd/httpd:2.4.66
```

This setup ensures flexibility in managing your Apache modules based on different requirements.


### 3. Environment-Specific Server Settings

The Docker image allows you to toggle between `production` and `development` settings by using the `HOST_ENV` environment variable:

- **Production Mode**: Hide server details.

    ```bash
    docker run -d -p 80:80 -p 443:443 -e HOST_ENV=production mxmd/httpd:2.4.66
    ```

- **Development Mode**: Display full server details.

    ```bash
    docker run -d -p 80:80 -p 443:443 -e HOST_ENV=development mxmd/httpd:2.4.66
    ```

## Checking Enabled Apache Modules

Upon starting the Docker container, the enabled Apache modules are printed to the console. To view them, you can check the container logs:

```bash
docker logs [container_id]
```

Replace `[container_id]` with your running container's ID.
