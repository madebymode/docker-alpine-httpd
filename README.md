
# Alpine Apache Docker Image with Custom Entrypoint

This Docker image provides an Apache server with an optional PHP-FPM backend. It allows for dynamic enabling of Apache modules and adjusts server settings based on environment variables.

## Building the Docker Image

First, make sure you've cloned the repository and you are inside the directory containing the Dockerfile:

```bash
docker build -t mxmd/httpd:2.4.58 .
```

## Running the Docker Image

You can run the image using:

```bash
docker run -d -p 80:80 -p 443:443 mxmd/httpd:2.4.58
```

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

You can enable additional Apache modules at runtime by passing the `APACHE_MODULES` environment variable. This variable should contain comma-separated values of the module's name and its path. You can get these paths by running `docker run --rm httpd:2.4-alpine cat /usr/local/apache2/conf/extra/httpd-default.conf`.

For example, to enable the `ratelimit_module` and `allowmethods_module`:

```bash
docker run -d -p 80:80 -p 443:443 -e APACHE_MODULES="ratelimit_module modules/mod_ratelimit.so,allowmethods_module modules/mod_allowmethods.so" mxmd/httpd:2.4.58
```

This setup ensures flexibility in managing your Apache modules based on different requirements.


### 3. Environment-Specific Server Settings

The Docker image allows you to toggle between `production` and `development` settings by using the `HOST_ENV` environment variable:

- **Production Mode**: Hide server details.

    ```bash
    docker run -d -p 80:80 -p 443:443 -e HOST_ENV=production mxmd/httpd:2.4.58
    ```

- **Development Mode**: Display full server details.

    ```bash
    docker run -d -p 80:80 -p 443:443 -e HOST_ENV=development mxmd/httpd:2.4.58
    ```

## Checking Enabled Apache Modules

Upon starting the Docker container, the enabled Apache modules are printed to the console. To view them, you can check the container logs:

```bash
docker logs [container_id]
```

Replace `[container_id]` with your running container's ID.
