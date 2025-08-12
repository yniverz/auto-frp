[![License: NCPUL](https://img.shields.io/badge/license-NCPUL-blue.svg)](./LICENSE.md)

# Auto-FRP

Auto-FRP is a simple automatic manager for [fatedier/frp](https://github.com/fatedier/frp), designed to work with [yniverz/python-nginx-dashboard](https://github.com/yniverz/python-nginx-dashboard). The dashboard allows configuration of FRP (Fast Reverse Proxy) Clients and Servers through a master server, and the Auto-FRP script will pull the latest configuration from the dashboard and apply it to the FRP client or server.

## Features

- **Easy Installation**: One-line script to set up Auto-FRP and all dependencies.  
- **Auto-Updates**: Automatically fetches and updates FRP to the latest release on startup.  
- **Systemd Service**: Installs a persistent service for FRP that restarts on failures.  
- **Quick Configuration**: Provides a helper script (`auto-frp-config`) to edit FRP’s config and automatically restart the service if changes are detected.  
- **Uninstallation**: Simple script to cleanly remove all traces of Auto-FRP from your system.

## Getting Started

### 1. Clone This Repository

```bash
git clone https://github.com/yniverz/auto-frp.git
cd auto-frp
```

### 2. Install Auto-FRP

```bash
sudo ./install.sh
```

- This script will:
  - Install Python 3, pip, and virtualenv if not already installed.
  - Copy files to `/opt/auto-frp` (by default).
  - Create a systemd service at `/etc/systemd/system/auto-frp.service`.
  - Create a dedicated Python virtual environment and install dependencies.
  - Start and enable the `auto-frp` service so it runs at boot.

### 3. Configure Auto-FRP

By default, Auto-FRP uses a template that sets it up in **client** mode (`type="client"` in `config.toml`).  
You can switch it to **server** mode by editing the config.

You can add multiple instances in the `config.toml` file by adding more sections of `[[instances]]`.
Check the `config.template.toml` file for an example configuration.

```toml
[[instances]]
type="client" # or "server"
id="your_id" # will be used to identify the client or server
master-base-url="https://master:8080" # base URL of the master server
master-token="your_master_token" # token for authentication with the master server
ssl-verify=true # whether to verify SSL certificates
```

Use the helper script `auto-frp-config`:

- **Edit Auto-FRP config**:
  ```bash
  auto-frp-config
  ```

- **See logs**:
  ```bash
  auto-frp-config -l
  ```

If you edit the config, Auto-FRP will detect changes and automatically restart the service.

### 4. Updating Auto-FRP

If you’ve pulled new changes from the repo or want to upgrade dependencies, run:

```bash
sudo ./update.sh
```

This will:
- Stop the `auto-frp` service.
- Copy updated `core` files to `/opt/auto-frp`.
- Update Python dependencies in the virtual environment.
- Restart the `auto-frp` service.

### 6. Uninstalling Auto-FRP

To completely remove Auto-FRP from your system:

```bash
sudo ./uninstall.sh
```

This will:
- Stop and disable the systemd service.
- Remove `/opt/auto-frp`, the systemd unit file, and the log file.
- Remove the `auto-frp-config` command from `/usr/local/bin`.
