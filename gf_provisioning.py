#!/usr/bin/env python3
import json
import os
import sys
import subprocess
import re
import shutil
import pexpect
import time
import select
import atexit
import uuid
import getpass

START_TIME = time.time()
LOG_FILE_PATH = f"provisioning_execution_{time.strftime('%Y%m%d_%H%M%S')}.log"

class DualLogger:
    def __init__(self, filepath):
        self.terminal = sys.stdout
        self.logfile = open(filepath, "a", encoding="utf-8")

    def write(self, message):
        self.terminal.write(message)
        if self.logfile and not self.logfile.closed:
            self.logfile.write(message)
        self.flush()

    def flush(self):
        self.terminal.flush()
        if self.logfile and not self.logfile.closed:
            self.logfile.flush()

    def close(self):
        if self.logfile and not self.logfile.closed:
            self.logfile.flush()
            os.fsync(self.logfile.fileno())
            self.logfile.close()

logger_instance = DualLogger(LOG_FILE_PATH)
sys.stdout = logger_instance
sys.stderr = logger_instance

def log_final_summary():
    elapsed_seconds = int(time.time() - START_TIME)
    minutes, seconds = divmod(elapsed_seconds, 60)
    time_str = f"{minutes} min {seconds} s" if minutes > 0 else f"{seconds} s"

    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    summary = (
        f"\n======================================================================\n"
        f" [LOG CLOSED] Fecha: {timestamp}\n"
        f" [LOG CLOSED] Tiempo total transcurrido: {time_str}\n"
        f"======================================================================\n"
    )
    print(summary)
    logger_instance.close()

atexit.register(log_final_summary)

STATE_FILE = "provisioning_state.json"
SUDO_PASSWORD = None
MIRROR_PASSWORD = None
VAULT_PASSWORD = r"/!X6i8n0+cxK$v3m4tQ-"
DEFAULT_NOMACHINE_URL = "https://download.nomachine.com/download/9.8/Linux/nomachine_9.8.2_1_amd64.deb"
GPG_KEY_IMPORT_CMD = (
    "wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | "
    "sudo gpg --dearmor --yes -o /etc/apt/trusted.gpg.d/google-chrome.gpg"
)

DHCPD_CONF_CONTENT = """# BEGIN ANSIBLE MANAGED BLOCK
ddns-update-style none;
ignore client-updates;
allow booting;
allow bootp;
ddns-updates off;
default-lease-time 6000;
max-lease-time 7200;
authoritative;
subnet 10.0.0.0 netmask 255.255.0.0 {
  option subnet-mask 255.255.0.0;
  option routers 10.0.0.254;
  option broadcast-address 10.0.255.255;
  next-server 10.0.0.254;

  filename "http://10.0.0.254:8001/pxelinux.0";
}
host izumi-1 { hardware ethernet 98:98:FB:CA:F0:E5; fixed-address 10.0.0.1; }
host izumi-2 { hardware ethernet 98:98:FB:CA:F1:85; fixed-address 10.0.0.2; }
host izumi-3 { hardware ethernet 98:98:FB:CB:06:DD; fixed-address 10.0.0.3; }
host izumi-4 { hardware ethernet 98:98:FB:CB:01:ED; fixed-address 10.0.0.4; }
host izumi-5 { hardware ethernet 98:98:FB:CA:D6:D5; fixed-address 10.0.0.5; }
host izumi-6 { hardware ethernet 98:98:FB:D0:DA:05; fixed-address 10.0.0.6; }
host izumi-7 { hardware ethernet 98:98:FB:CB:06:E5; fixed-address 10.0.0.7; }
host izumi-8 { hardware ethernet 98:98:FB:C5:98:8D; fixed-address 10.0.0.8; }
host izumi-9 { hardware ethernet 98:98:FB:CF:26:55; fixed-address 10.0.0.9; }
host izumi-10 { hardware ethernet 98:98:FB:CB:0D:85; fixed-address 10.0.0.10; }
host izumi-11 { hardware ethernet 98:98:FB:CF:25:3D; fixed-address 10.0.0.11; }
host izumi-12 { hardware ethernet 98:98:FB:CA:E6:05; fixed-address 10.0.0.12; }
host izumi-13 { hardware ethernet 98:98:FB:CB:6E:95; fixed-address 10.0.0.13; }
host izumi-14 { hardware ethernet 98:98:FB:D0:E7:25; fixed-address 10.0.0.14; }
host izumi-15 { hardware ethernet 98:98:FB:CA:E5:F5; fixed-address 10.0.0.15; }
host izumi-16 { hardware ethernet 98:98:FB:C5:33:3D; fixed-address 10.0.0.16; }
host rj45-switch { hardware ethernet 00:00:00:00:00:00; fixed-address 10.0.0.249; }

# END ANSIBLE MANAGED BLOCK
host zpe { hardware ethernet e4:1a:2c:02:c3:0c; fixed-address 10.0.0.253; }
host iboot { hardware ethernet 00:0D:AD:04:92:28; fixed-address 10.0.0.250; }
host tross { hardware ethernet C0:1C:6A:66:C2:E4; fixed-address 10.0.0.251; }
  filename "http://10.0.0.254:8001/pxelinux.0";"""

DHCPD6_CONF_CONTENT = """# BEGIN ANSIBLE MANAGED BLOCK
ddns-update-style none;
ignore client-updates;
allow booting;
allow bootp;
ddns-updates off;
default-lease-time 6000;
max-lease-time 7200;
authoritative;
option domain-search-list code 119 = text;
option dhcp6.bootfile-url code 59 = string;
option dhcp6.name-servers fd00::9;

subnet6 fd00::/64 {
range6 fd00::11 fd00::FF;
option dhcp6.bootfile-url "http://[fd00::9]:8001/diorite/ipxe.cfg";
log(info, "DHCPv6 - Found other ipv6 client...");

host diorite-1 {
host-identifier option dhcp6.client-id  00:03:00:01:98:98:FB:CA:F0:E2;
log(info, "DHCPv6 - Found Diorite-1 client...");
fixed-address6 fd00::10;
}
host diorite-2 {
host-identifier option dhcp6.client-id  00:03:00:01:98:98:FB:CA:F1:82;
log(info, "DHCPv6 - Found Diorite-2 client...");
fixed-address6 fd00::11;
}
host diorite-3 {
host-identifier option dhcp6.client-id  00:03:00:01:98:98:FB:CB:06:DA;
log(info, "DHCPv6 - Found Diorite-3 client...");
fixed-address6 fd00::12;
}
host diorite-4 {
host-identifier option dhcp6.client-id  00:03:00:01:98:98:FB:CB:01:EA;
log(info, "DHCPv6 - Found Diorite-4 client...");
fixed-address6 fd00::13;
}
host diorite-5 {
host-identifier option dhcp6.client-id  00:03:00:01:98:98:FB:CA:D6:D2;
log(info, "DHCPv6 - Found Diorite-5 client...");
fixed-address6 fd00::14;
}
host diorite-6 {
host-identifier option dhcp6.client-id  00:03:00:01:98:98:FB:D0:DA:02;
log(info, "DHCPv6 - Found Diorite-6 client...");
fixed-address6 fd00::15;
}
host diorite-7 {
host-identifier option dhcp6.client-id  00:03:00:01:98:98:FB:CB:06:E2;
log(info, "DHCPv6 - Found Diorite-7 client...");
fixed-address6 fd00::16;
}
host diorite-8 {
host-identifier option dhcp6.client-id  00:03:00:01:98:98:FB:C5:98:8A;
log(info, "DHCPv6 - Found Diorite-8 client...");
fixed-address6 fd00::17;
}
host diorite-9 {
host-identifier option dhcp6.client-id  00:03:00:01:98:98:FB:CF:26:52;
log(info, "DHCPv6 - Found Diorite-9 client...");
fixed-address6 fd00::18;
}
host diorite-10 {
host-identifier option dhcp6.client-id  00:03:00:01:98:98:FB:CB:0D:82;
log(info, "DHCPv6 - Found Diorite-10 client...");
fixed-address6 fd00::19;
}
host diorite-11 {
host-identifier option dhcp6.client-id  00:03:00:01:98:98:FB:CF:25:3A;
log(info, "DHCPv6 - Found Diorite-11 client...");
fixed-address6 fd00::1A;
}
host diorite-12 {
host-identifier option dhcp6.client-id  00:03:00:01:98:98:FB:CA:E6:02;
log(info, "DHCPv6 - Found Diorite-12 client...");
fixed-address6 fd00::1B;
}
host diorite-13 {
host-identifier option dhcp6.client-id  00:03:00:01:98:98:FB:CB:6E:92;
log(info, "DHCPv6 - Found Diorite-13 client...");
fixed-address6 fd00::1C;
}
host diorite-14 {
host-identifier option dhcp6.client-id  00:03:00:01:98:98:FB:D0:E7:22;
log(info, "DHCPv6 - Found Diorite-14 client...");
fixed-address6 fd00::1D;
}
host diorite-15 {
host-identifier option dhcp6.client-id  00:03:00:01:98:98:FB:CA:E5:F2;
log(info, "DHCPv6 - Found Diorite-15 client...");
fixed-address6 fd00::1E;
}
host diorite-16 {
host-identifier option dhcp6.client-id  00:03:00:01:98:98:FB:C5:33:3A;
log(info, "DHCPv6 - Found Diorite-16 client...");
fixed-address6 fd00::1F;
}
}
# END ANSIBLE MANAGED BLOCK"""

def print_ascii_fail(message="Se detecto un error durante la ejecucion."):
    red = "\033[91m\033[1m"
    reset = "\033[0m"
    width = 66
    print(f"\n{red}┌{'─' * width}┐{reset}")
    print(f"{red}│{'✗  FALLO'.center(width)}│{reset}")
    print(f"{red}├{'─' * width}┤{reset}")
    for line in [message, "Revisa el log de arriba para mas detalle."]:
        print(f"{red}│ {line[:width-2].ljust(width-2)} │{reset}")
    print(f"{red}└{'─' * width}┘{reset}\n")

def print_ascii_pass(message="Mirror de apt + Ansible Playbook: OK."):
    green = "\033[92m\033[1m"
    reset = "\033[0m"
    width = 66
    print(f"\n{green}┌{'─' * width}┐{reset}")
    print(f"{green}│{'✓  OK'.center(width)}│{reset}")
    print(f"{green}├{'─' * width}┤{reset}")
    print(f"{green}│ {message[:width-2].ljust(width-2)} │{reset}")
    print(f"{green}└{'─' * width}┘{reset}\n")

_state_perms_fixed = False

def fix_state_file_permissions():
    global _state_perms_fixed
    if _state_perms_fixed:
        return
    if os.path.exists(STATE_FILE):
        sudo_user = os.environ.get('SUDO_USER', 'testusr')
        subprocess.run(f"sudo chown {sudo_user}:{sudo_user} {STATE_FILE}", shell=True, stderr=subprocess.DEVNULL)
        _state_perms_fixed = True

def _atomic_write_json(filepath, data):
    if os.path.exists(filepath):
        try:
            shutil.copyfile(filepath, filepath + ".bak")
        except Exception as e:
            print(f"[!] Advertencia: no se pudo generar el respaldo de '{filepath}' ({e}).")
    tmp_path = f"{filepath}.tmp.{os.getpid()}"
    with open(tmp_path, "w") as f:
        json.dump(data, f, indent=4)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_path, filepath)

def _load_json_state(filepath):
    if not os.path.exists(filepath):
        return {"flags": {}, "config": {}}
    try:
        with open(filepath, "r") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        backup_path = filepath + ".bak"
        print(f"[!] Advertencia: '{filepath}' esta corrupto (JSON invalido: {e}).")
        if os.path.exists(backup_path):
            try:
                with open(backup_path, "r") as f:
                    data = json.load(f)
                print(f"[*] Se recupero el respaldo '{backup_path}' correctamente. "
                      f"Puede faltar el ultimo cambio que no llego a guardarse.")
                return data
            except json.JSONDecodeError:
                print(f"[!] El respaldo '{backup_path}' tambien esta corrupto.")
        raise RuntimeError(
            f"El archivo de estado '{filepath}' esta corrupto (JSON invalido) y no se "
            f"pudo recuperar desde su respaldo ('{backup_path}'). Revisalo/corregilo "
            f"manualmente, o borralo si preferis empezar de cero para este archivo, "
            f"antes de volver a correr el script."
        ) from e

def load_state():
    fix_state_file_permissions()
    return _load_json_state(STATE_FILE)

def save_state(state):
    fix_state_file_permissions()
    _atomic_write_json(STATE_FILE, state)

def is_step_completed(step_name):
    state = load_state()
    return state.get("flags", {}).get(step_name, False)

def mark_step_completed(step_name, extra_config=None):
    state = load_state()
    state["flags"][step_name] = True
    if extra_config:
        state["config"].update(extra_config)
    save_state(state)
    print(f"[✓] Paso '{step_name}' completado y registrado en {STATE_FILE}.")

TROSS_STATE_FILE = "tross_config.json"
_tross_state_perms_fixed = False

def fix_tross_state_file_permissions():
    global _tross_state_perms_fixed
    if _tross_state_perms_fixed:
        return
    if os.path.exists(TROSS_STATE_FILE):
        sudo_user = os.environ.get('SUDO_USER', 'testusr')
        subprocess.run(f"sudo chown {sudo_user}:{sudo_user} {TROSS_STATE_FILE}", shell=True,
                        stderr=subprocess.DEVNULL)
        _tross_state_perms_fixed = True

def load_tross_state():
    fix_tross_state_file_permissions()
    return _load_json_state(TROSS_STATE_FILE)

def save_tross_state(state):
    fix_tross_state_file_permissions()
    _atomic_write_json(TROSS_STATE_FILE, state)

def is_tross_step_completed(step_name):
    state = load_tross_state()
    return state.get("flags", {}).get(step_name, False)

def mark_tross_step_completed(step_name, extra_config=None):
    state = load_tross_state()
    state["flags"][step_name] = True
    if extra_config:
        state["config"].update(extra_config)
    save_tross_state(state)
    print(f"[✓] Paso '{step_name}' completado y registrado en {TROSS_STATE_FILE}.")

def _prompt_password_twice(label):
    while True:
        p1 = getpass.getpass(f"Ingresa la contraseña de {label}: ")
        if not p1:
            print("[!] La contraseña no puede estar vacia. Intenta de nuevo.\n")
            continue
        p2 = getpass.getpass(f"Confirma la contraseña de {label}: ")
        if p1 != p2:
            print("[!] Las contraseñas no coinciden. Intenta de nuevo.\n")
            continue
        return p1

def ensure_credentials():
    global SUDO_PASSWORD, MIRROR_PASSWORD

    state = load_state()
    creds = state.get("config", {}).get("_credentials", {})
    stored_sudo = creds.get("sudo_password")
    stored_mirror = creds.get("mirror_password")

    if stored_sudo and stored_mirror:
        SUDO_PASSWORD = stored_sudo
        MIRROR_PASSWORD = stored_mirror
        print("[=] Credenciales ya configuradas previamente. Cargando desde el state file...")
        return

    print("--- Configuracion inicial de credenciales ---")
    print("Esto solo se pide una vez por equipo; quedan guardadas en el state file")
    print("para esta y futuras ejecuciones (incluidos los reinicios a mitad del proceso).\n")

    SUDO_PASSWORD = stored_sudo or _prompt_password_twice("sudo (usuario local del equipo)")
    MIRROR_PASSWORD = stored_mirror or _prompt_password_twice("del usuario 'testusr' en el Git-Mirror (172.24.125.2)")

    state = load_state()
    state.setdefault("config", {})["_credentials"] = {
        "sudo_password": SUDO_PASSWORD,
        "mirror_password": MIRROR_PASSWORD,
    }
    save_state(state)

    subprocess.run(f"sudo chmod 600 {STATE_FILE}", shell=True, check=False)

    print(f"[✓] Credenciales guardadas en {STATE_FILE} (permisos restringidos a 600).\n")

def _activate_sudo():
    try:
        res = subprocess.run(
            f'echo "{SUDO_PASSWORD}" | sudo -S -v',
            shell=True,
            capture_output=True,
            text=True,
            timeout=15
        )
        if res.returncode != 0:
            print(f"[!] Advertencia: no se pudo activar/refrescar sudo automaticamente "
                  f"({res.stderr.strip()}).")
        return res.returncode == 0
    except Exception as e:
        print(f"[!] Advertencia: excepcion al activar/refrescar sudo automaticamente ({e}).")
        return False

def run_command(cmd, check=True):
    print(f"[CMD] {cmd}")
    res = subprocess.run(cmd, shell=True, stderr=subprocess.PIPE, text=True)
    if res.stderr:
        sys.stderr.write(res.stderr)
    if check and res.returncode != 0:
        err_detail = res.stderr.strip() if res.stderr else "(sin salida en stderr)"
        raise RuntimeError(f"Error ejecutando comando: {cmd} (rc={res.returncode}). stderr: {err_detail}")
    return res.returncode

def run_interactive(cmd, timeout=3600):
    print(f"[CMD Interactive] {cmd}")
    child = pexpect.spawn("bash", ["-c", cmd], encoding="utf-8", timeout=timeout)
    child.logfile_read = sys.stdout

    while True:
        idx = child.expect([
            r"\[sudo\] password for .*:?",
            r"[pP]assword:",
            pexpect.EOF,
            pexpect.TIMEOUT
        ], timeout=600)

        if idx == 0 or idx == 1:
            child.sendline(SUDO_PASSWORD)
        elif idx == 2:
            break
        elif idx == 3:
            child.close()
            raise RuntimeError(f"Timeout en comando interactivo: {cmd}")

    child.close()
    if child.exitstatus != 0:
        raise RuntimeError(f"Error en comando interactivo: {cmd} (Exit code: {child.exitstatus})")
    return child.exitstatus

def _retry_download(fn, description, max_retries=3, base_delay=10):
    last_exc = None
    for attempt in range(1, max_retries + 1):
        try:
            return fn()
        except Exception as e:
            last_exc = e
            print(f"[!] Intento {attempt}/{max_retries} de '{description}' fallo: {e}")
            if attempt < max_retries:
                delay = base_delay * (2 ** (attempt - 1))
                print(f"[*] Reintentando '{description}' en {delay}s...")
                time.sleep(delay)
    raise RuntimeError(f"'{description}' fallo tras {max_retries} intentos. Ultimo error: {last_exc}")

def set_ID():
    if is_step_completed("set_ID"):
        print("[=] Paso 'set_ID' ya fue ejecutado previamente. Omitiendo...")
        return

    print("--- PASO 1: Configuracion de ID de Rack ---")
    rack_num_str = input("Ingresa el numero de rack (ej. 90 o 54): ").strip()
    
    if not rack_num_str.isdigit():
        raise ValueError("El numero de rack debe ser un valor numerico.")

    rack_num = int(rack_num_str)
    
    last_octet = rack_num + 99
    if last_octet > 254:
        raise ValueError(f"El octeto calculado ({last_octet}) excede el rango valido de IP.")
        
    ip_address = f"172.24.125.{last_octet}"
    hostname = f"ghostfish-ist-flg-{rack_num:03d}"

    config_data = {
        "rack_number": rack_num,
        "ip_address": ip_address,
        "hostname": hostname
    }

    print(f"\n[+] Rack Numero: {rack_num}")
    print(f"[+] IP Calculada: {ip_address}")
    print(f"[+] Hostname Asignado: {hostname}\n")

    mark_step_completed("set_ID", config_data)

def set_network():
    if is_step_completed("set_network"):
        print("[=] Paso 'set_network' ya fue ejecutado previamente. Omitiendo...")
        return

    print("--- PASO 2: Configuracion de Red y Paquetes Base ---")
    state = load_state()
    ip_address = state.get("config", {}).get("ip_address")

    if not ip_address:
        raise RuntimeError("No se encontro la IP en la configuracion. Asegurate de correr 'set_ID' primero.")

    nmcli_cmd = (
        f'sudo nmcli con add con-name "SFC" ifname eno1 type ethernet '
        f'ipv4.method manual ipv4.addresses {ip_address}/24 gw4 172.24.125.1 ipv4.dns 8.8.8.8'
    )
    run_interactive(nmcli_cmd)

    print("[*] Verificando e importando llaves GPG faltantes para apt...")
    _retry_download(lambda: run_interactive(GPG_KEY_IMPORT_CMD), "descarga de llave GPG de Google")

    apt_install([
        "openssh-server", "net-tools", "git", "sssd", "sssd-tools",
        "libpam-sss", "libnss-sss", "python3-pip",
    ])

    print("[*] Instalando dependencias iniciales de pip3...")
    run_interactive("sudo pip3 install colorlog jsonpickle google.cloud --upgrade")

    sudo_user = os.environ.get('SUDO_USER', 'testusr')
    user_home = f"/home/{sudo_user}"
    ssh_key_path = os.path.join(user_home, ".ssh/id_rsa")
    
    if not os.path.exists(ssh_key_path):
        print("[*] Generando llaves SSH (ssh-keygen)...")
        cmd = f"ssh-keygen -t rsa -N \"\" -f {ssh_key_path}"
        run_command(cmd)
        print("[✓] Llaves SSH generadas exitosamente.")
    else:
        print(f"[=] La llave SSH ya existe en {ssh_key_path}. Omitiendo ssh-keygen...")

    mark_step_completed("set_network")

def _run_scp_from_mirror_once(remote_path, local_destination):
    mirror_ip = "172.24.125.2"
    cmd = f"scp testusr@{mirror_ip}:{remote_path} {local_destination}"
    print(f"[CMD] Copiando desde Mirror: {cmd}")

    child = pexpect.spawn(cmd, encoding="utf-8", timeout=30)
    
    while True:
        idx = child.expect([
            r"Are you sure you want to continue connecting \(yes/no/\[fingerprint\]\)\?",
            r"[pP]assword:",
            pexpect.EOF,
            pexpect.TIMEOUT
        ])
        
        if idx == 0:
            child.sendline("yes")
        elif idx == 1:
            child.sendline(MIRROR_PASSWORD)
        elif idx == 2:
            break
        elif idx == 3:
            child.close()
            raise RuntimeError(f"Timeout copiando {remote_path} desde el Git Mirror.")

    child.close()
    if child.exitstatus != 0:
        raise RuntimeError(f"Error transfiriendo {remote_path} desde el Git Mirror.")

def run_scp_from_mirror(remote_path, local_destination):
    _retry_download(
        lambda: _run_scp_from_mirror_once(remote_path, local_destination),
        f"SCP de {remote_path} desde el Git-Mirror"
    )

def gitconfig_cookie():
    if is_step_completed("gitconfig_cookie"):
        print("[=] Paso 'gitconfig_cookie' ya fue ejecutado previamente. Omitiendo...")
        return

    print("--- PASO 3: Git Config & Security Repository Setup ---")
    state = load_state()
    ip_address = state.get("config", {}).get("ip_address")

    if not ip_address:
        raise RuntimeError("No se encontro la IP en la configuracion. Asegurate de correr 'set_ID' primero.")

    sudo_user = os.environ.get('SUDO_USER', 'testusr')
    user_home = f"/home/{sudo_user}"

    run_scp_from_mirror("~/.gitconfig", f"{user_home}/")
    run_scp_from_mirror("~/.gitcookies", f"{user_home}/")

    sec_repo_path = os.path.join(user_home, "security-hardened-image")
    if not os.path.exists(sec_repo_path):
        print("[*] Clonando repo security-hardened-image...")
        clone_cmd = f"git clone https://mfg-partners.googlesource.com/security-hardened-image {sec_repo_path}"
        run_command(clone_cmd)
    else:
        print("[=] El repositorio 'security-hardened-image' ya existe. Omitiendo clonacion...")

    run_scp_from_mirror("security-read-flg.json", f"{user_home}/")
    mark_step_completed("gitconfig_cookie")

def flex_tag():
    if is_step_completed("flex_tag"):
        print("[=] Paso 'flex_tag' ya fue ejecutado previamente. Omitiendo...")
        return

    print("--- PASO 4: Flex Tagging & Patch Script Setup ---")
    sudo_user = os.environ.get('SUDO_USER', 'testusr')
    user_home = f"/home/{sudo_user}"
    patch_script_path = os.path.join(user_home, "security-hardened-image/scripts/setup-patch.sh")

    if not os.path.exists(patch_script_path):
        raise FileNotFoundError(f"No se encontró el archivo: {patch_script_path}")

    with open(patch_script_path, "r") as f:
        content = f.read()

    content = re.sub(
        r"^export CROWDSTRIKE_TAGS=.*$",
        "export CROWDSTRIKE_TAGS=Flex_Guadalajara_PROD",
        content,
        flags=re.MULTILINE
    )

    content = re.sub(
        r"^\s*\./scripts/prepare-dvc\.sh",
        "#./scripts/prepare-dvc.sh",
        content,
        flags=re.MULTILINE
    )

    with open(patch_script_path, "w") as f:
        f.write(content)
    
    print("[✓] Modificaciones aplicadas a setup-patch.sh.")

    print("[*] Añadiendo llave GPG mediante apt-key...")
    apt_key_cmd = "sudo apt-key adv --keyserver hkp://keyserver.ubuntu.com:80 --recv-keys 32EE5355A6BC6E42"
    run_interactive(apt_key_cmd)

    mark_step_completed("flex_tag")

def run_security_patch():
    if is_step_completed("run_security_patch"):
        print("[=] Paso 'run_security_patch' ya fue ejecutado previamente. Omitiendo...")
        return

    print("--- PASO 5: Ejecución de setup-patch.sh ---")
    sudo_user = os.environ.get('SUDO_USER', 'testusr')
    user_home = f"/home/{sudo_user}"
    sec_dir = os.path.join(user_home, "security-hardened-image")
    patch_script = os.path.join(sec_dir, "scripts/setup-patch.sh")

    if not os.path.exists(patch_script):
        raise FileNotFoundError(f"No se encontró el script en: {patch_script}")

    run_command(f"chmod +x {patch_script}")
    run_interactive(f"sudo chown -R {sudo_user}:{sudo_user} {sec_dir}")

    cmd = f"cd {sec_dir} && ./scripts/setup-patch.sh"
    run_interactive(cmd, timeout=3600)

    mark_step_completed("run_security_patch")

def validate_and_lego_setup():
    if is_step_completed("validate_and_lego_setup"):
        print("[=] Paso 'validate_and_lego_setup' ya fue ejecutado previamente. Omitiendo...")
        return

    print("--- PASO 6: Validacion de Parches y Configuracion de Lego-Infra ---")
    sudo_user = os.environ.get('SUDO_USER', 'testusr')
    user_home = f"/home/{sudo_user}"
    sec_op_dir = os.path.join(user_home, "security-hardened-image/security_features_operation")

    print("[*] Ejecutando validacion de parches de seguridad...")
    val_cmd = f"cd {sec_op_dir} && python3 ./security_features_operator.py -c ansible.cfg -a validate"
    run_interactive(val_cmd, timeout=600)

    print("[*] Agregando repositorio universe e instala librerias pip de Google...")
    run_interactive("sudo add-apt-repository universe -y")
    run_interactive("sudo pip3 install google-cloud-appengine-logging google-cloud-audit-log google-cloud-logging")

    lego_dir = os.path.join(user_home, "lego-infra")
    if not os.path.exists(lego_dir):
        print("[*] Clonando repo lego-infra...")
        clone_cmd = f"git clone https://mfg-partners.googlesource.com/lego-infra {lego_dir}"
        run_command(clone_cmd)
    else:
        print("[=] El repositorio 'lego-infra' ya existe. Omitiendo clonacion...")

    ansible_script_dir = os.path.join(lego_dir, "lego_setup/ansible_installation_script")
    print("[*] Ejecutando install-ansible-clean.sh...")
    ansible_cmd = f"cd {ansible_script_dir} && chmod +x install-ansible-clean.sh && ./install-ansible-clean.sh"
    run_interactive(ansible_cmd, timeout=1200)

    print("[*] Instalando librerias finales con pip3...")
    run_interactive("sudo pip3 install colorlog jsonpickle google.cloud")

    mark_step_completed("validate_and_lego_setup")

def setup_nomachine_yaml():
    if is_step_completed("setup_nomachine_yaml"):
        print("[=] Paso 'setup_nomachine_yaml' ya fue ejecutado previamente. Omitiendo...")
        return

    print("--- PASO 7: Actualizacion de URL NoMachine en YAML ---")
    sudo_user = os.environ.get('SUDO_USER', 'testusr')
    yaml_path = f"/home/{sudo_user}/lego-infra/lego_setup/lego_abmx_test_server/install-nomachine.yaml"

    if not os.path.exists(yaml_path):
        raise FileNotFoundError(f"No se encontró el archivo: {yaml_path}")

    state = load_state()
    nomachine_url = state.get("config", {}).get("nomachine_url", DEFAULT_NOMACHINE_URL)

    print(f"[+] Usando URL de NoMachine: {nomachine_url}")

    with open(yaml_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    updated = False
    pattern = r'deb:\s*["\']?\{\{\s*nomachine_deb\s*\}\}["\']?'

    target_idx = 98
    if target_idx < len(lines) and re.search(pattern, lines[target_idx]):
        lines[target_idx] = re.sub(pattern, f'deb: "{nomachine_url}"', lines[target_idx])
        updated = True
    else:
        for i, line in enumerate(lines):
            if re.search(pattern, line):
                lines[i] = re.sub(pattern, f'deb: "{nomachine_url}"', line)
                updated = True
                break

    if not updated:
        raise RuntimeError("No se encontro el patron 'deb: \"{{ nomachine_deb }}\"' en install-nomachine.yaml")

    with open(yaml_path, "w", encoding="utf-8") as f:
        f.writelines(lines)

    print(f"[✓] Archivo {yaml_path} actualizado exitosamente.")
    mark_step_completed("setup_nomachine_yaml", {"nomachine_url": nomachine_url})

APT_CANDIDATE_MIRRORS = [
    "http://us.archive.ubuntu.com/ubuntu/",
    "http://archive.ubuntu.com/ubuntu/",
    "http://mirrors.edge.kernel.org/ubuntu/",
    "http://mirror.math.princeton.edu/pub/ubuntu/",
    "http://azure.archive.ubuntu.com/ubuntu/",
]

APT_SOURCES_FILE = "/etc/apt/sources.list"
APT_SOURCES_BACKUP = "/etc/apt/sources.list.bak-provisioning"


def _probe_mirror(mirror_url, connect_timeout=15):
    probe = subprocess.run(
        f'curl -s -o /dev/null -w "%{{http_code}}" --max-time {connect_timeout} {mirror_url}',
        shell=True, capture_output=True, text=True
    )
    http_code = probe.stdout.strip()
    return probe.returncode == 0 and http_code.startswith(("2", "3")), http_code


def _backup_sources_list_once():
    if not os.path.exists(APT_SOURCES_BACKUP):
        subprocess.run(f"sudo cp {APT_SOURCES_FILE} {APT_SOURCES_BACKUP}", shell=True, check=False)


def _restore_sources_list():
    if os.path.exists(APT_SOURCES_BACKUP):
        subprocess.run(f"sudo cp {APT_SOURCES_BACKUP} {APT_SOURCES_FILE}", shell=True, check=False)


def _point_sources_list_to_mirror(mirror_url):
    sed_cmd = (
        r"sudo sed -i -E "
        r"'s#https?://[a-zA-Z0-9.-]+/ubuntu/#" + mirror_url.replace("/", r"\/") + r"#g' "
        + APT_SOURCES_FILE
    )
    subprocess.run(sed_cmd, shell=True, check=False)


def _apt_with_mirror_fallback(apt_command, description, max_retries_per_mirror=2,
                               base_delay=10, connect_timeout=15):
    _backup_sources_list_once()

    for mirror_url in APT_CANDIDATE_MIRRORS:
        print(f"[*] Probando mirror: {mirror_url}")
        reachable, http_code = _probe_mirror(mirror_url, connect_timeout)

        if not reachable:
            print(f"[!] Mirror no respondio (HTTP '{http_code}'). Probando el siguiente...")
            continue

        print(f"[✓] Mirror respondio HTTP {http_code}. Apuntando sources.list a este mirror...")
        _point_sources_list_to_mirror(mirror_url)

        for attempt in range(1, max_retries_per_mirror + 1):
            print(f"[*] apt-get update (mirror={mirror_url}, intento {attempt}/{max_retries_per_mirror})...")
            update_res = subprocess.run("sudo apt-get update", shell=True, capture_output=True, text=True)

            if update_res.returncode != 0:
                print(f"[!] 'apt-get update' fallo (rc={update_res.returncode}). "
                      f"stderr: {update_res.stderr.strip()[:300]}")
            else:
                print(f"[*] {description} (mirror={mirror_url}, intento {attempt}/{max_retries_per_mirror})...")
                cmd_res = subprocess.run(apt_command, shell=True, capture_output=True, text=True)
                if cmd_res.returncode == 0:
                    print(f"[✓] '{description}' completado correctamente con {mirror_url}.")
                    return mirror_url
                else:
                    print(f"[!] '{description}' fallo (rc={cmd_res.returncode}). "
                          f"stderr: {cmd_res.stderr.strip()[:500]}")

            if attempt < max_retries_per_mirror:
                delay = base_delay * (2 ** (attempt - 1))
                print(f"[*] Reintentando en {delay}s con el mismo mirror...")
                time.sleep(delay)

        print(f"[!] {mirror_url} agoto sus reintentos para '{description}'. Probando el siguiente mirror...")

    _restore_sources_list()
    raise RuntimeError(
        f"No se pudo completar '{description}' con ninguno de los mirrors probados "
        f"({', '.join(APT_CANDIDATE_MIRRORS)}). Se restauro el sources.list original. "
        f"Verifica la conectividad de red del host o agrega un mirror interno "
        f"confiable al inicio de APT_CANDIDATE_MIRRORS."
    )


def apt_update():
    return _apt_with_mirror_fallback("true", "apt-get update")


def apt_install(pkgs, update=True):
    pkgs_str = pkgs if isinstance(pkgs, str) else " ".join(pkgs)
    install_cmd = f"sudo DEBIAN_FRONTEND=noninteractive apt-get install -y {pkgs_str}"

    if update:
        return _apt_with_mirror_fallback(install_cmd, f"apt-get install -y {pkgs_str}")

    for attempt in range(1, 3):
        res = subprocess.run(install_cmd, shell=True, capture_output=True, text=True)
        if res.returncode == 0:
            print(f"[✓] apt-get install -y {pkgs_str} completado.")
            return True
        print(f"[!] Intento {attempt}/2 de 'apt-get install -y {pkgs_str}' fallo: "
              f"{res.stderr.strip()[:300]}")
        time.sleep(10)
    raise RuntimeError(f"No se pudo instalar {pkgs_str} tras 2 intentos (update=False).")


def ensure_apt_mirror_ready(max_retries_per_mirror=2, base_delay=10, connect_timeout=15):
    _apt_with_mirror_fallback(
        "sudo DEBIAN_FRONTEND=noninteractive apt-get dist-upgrade -y",
        "apt-get dist-upgrade -y",
        max_retries_per_mirror=max_retries_per_mirror,
        base_delay=base_delay,
        connect_timeout=connect_timeout,
    )
    return True


def ensure_dhcp():
    if is_step_completed("ensure_dhcp"):
        print("[=] Paso 'ensure_dhcp' ya fue ejecutado previamente. Omitiendo...")
        return
    print("--- PASO: Asegurar configuracion de DHCP ---")

    _scp_download("testusr", "172.24.125.136", "/etc/dhcp/dhcpd.conf", ".")
    _scp_download("testusr", "172.24.125.136", "/etc/dhcp/dhcpd6.conf", ".")

    _run_shell_sequence([
        "sudo mv dhcpd.conf /etc/dhcp/",
        "sudo mv dhcpd6.conf /etc/dhcp/",
        "sudo systemctl restart isc-dhcp-server",
        "sudo systemctl restart isc-dhcp-server6",
    ])

    print("[✓] Configuracion de DHCP actualizada y servicios reiniciados.")
    mark_step_completed("ensure_dhcp")

def run_ansible_playbook():
    if is_step_completed("run_ansible_playbook"):
        print("[=] Paso 'run_ansible_playbook' ya fue ejecutado previamente. Omitiendo...")
        return

    print("--- PASO 8: Ejecucion de Ansible Playbook ---")
    state = load_state()
    hostname = state.get("config", {}).get("hostname")

    if not hostname:
        raise RuntimeError("No se encontro el hostname en la configuracion. Asegurate de correr 'set_ID' primero.")

    print("[*] Pre-flight: verificando mirror de apt antes de invocar Ansible...")
    ensure_apt_mirror_ready()

    pip_upgrade_cmd = 'sudo python3.10 -m pip install --upgrade pip'
    downgrade_cmd = 'sudo python3.10 -m pip install "setuptools<70.0.0"'

    print("[*] Actualizando pip a la ultima version...")
    run_interactive(pip_upgrade_cmd)

    print("[*] Aplicando downgrade de setuptools PRE-Ansible...")
    run_interactive(downgrade_cmd)

    sudo_user = os.environ.get('SUDO_USER', 'testusr')
    playbook_dir = f"/home/{sudo_user}/lego-infra/lego_setup/lego_abmx_test_server"

    cmd = (
        f"cd {playbook_dir} && "
        f"ansible-playbook -i localhost, lego_abmx_test_server_setup.yml -vv "
        f"--ask-become-pass --connection=local --vault-id @prompt --flush-cache"
    )

    print(f"[CMD Interactive] {cmd}")
    child = pexpect.spawn("bash", ["-c", cmd], encoding="utf-8", timeout=None)
    
    output_buffer = ""

    class PexpectLogger:
        def write(self, text):
            nonlocal output_buffer
            sys.stdout.write(text)
            sys.stdout.flush()
            output_buffer += text

        def flush(self):
            sys.stdout.flush()

    child.logfile_read = PexpectLogger()

    while True:
        idx = child.expect([
            r"BECOME password:",
            r"Vault password \(default\):",
            r"Do you want to continue\?",
            r"Was lego bootstrap script",
            r"Enter Test Network Interface",
            r"Enter VPN Network Interface",
            r"Enter SFC Network Interface",
            r"Enter Tross Network Interface",
            r"Are the values correct\?",
            r"do you want to replace it\?",
            r"Enter computer name",
            r"Press Enter to exit and view the task timing summary",
            pexpect.EOF
        ], timeout=None)

        if idx == 0:
            child.sendline(SUDO_PASSWORD)
        elif idx == 1:
            child.sendline(VAULT_PASSWORD)
        elif idx in (2, 3):
            child.sendline("yes")
        elif idx == 4:
            child.sendline("ens4f0")
        elif idx in (5, 6, 7):
            child.sendline("none")
        elif idx in (8, 9):
            child.sendline("yes")
        elif idx == 10:
            print(f"\n[*] Enviando hostname configurado: {hostname}")
            child.sendline(hostname)
        elif idx == 11:
            print("\n[*] Detectado prompt de salida (task timing). Enviando ENTER...")
            child.sendline("")
        elif idx == 12:
            break

    child.close()

    print("[*] Reactivando sudo de forma automatica tras el comando de ansible...")
    _activate_sudo()

    failed_match = re.search(r"failed=(\d+)", output_buffer)
    if failed_match:
        failed_count = int(failed_match.group(1))
        if failed_count > 0:
            print_ascii_fail(f"Ansible reporto {failed_count} tarea(s) fallida(s) (failed > 0).")
            raise RuntimeError(f"Ansible Playbook finalizo con {failed_count} tarea(s) fallida(s).")

    if child.exitstatus != 0:
        print_ascii_fail("Error en ejecucion de ansible-playbook.")
        raise RuntimeError(f"Error en ejecucion de ansible-playbook (Exit code: {child.exitstatus})")

    print_ascii_pass()

    print("[*] Aplicando downgrade de setuptools POST-Ansible...")
    run_interactive(downgrade_cmd)
    
    mark_step_completed("run_ansible_playbook")
    print("[*] Esperando 15 segundos antes de finalizar el paso...")
    time.sleep(15)

def provisional_dhcp():
    if is_step_completed("provisional_dhcp"):
        print("[=] Paso 'provisional_dhcp' ya fue ejecutado previamente. Omitiendo...")
        return

    print("--- PASO 9: Configuracion de Archivos DHCP Provisionales ---")

    print("[*] Creando /etc/dhcp/dhcpd.conf...")
    cmd_dhcpd = f"echo '{DHCPD_CONF_CONTENT}' | sudo tee /etc/dhcp/dhcpd.conf > /dev/null"
    run_interactive(cmd_dhcpd)

    print("[*] Creando /etc/dhcp/dhcpd6.conf...")
    cmd_dhcpd6 = f"echo '{DHCPD6_CONF_CONTENT}' | sudo tee /etc/dhcp/dhcpd6.conf > /dev/null"
    run_interactive(cmd_dhcpd6)

    print("[*] Reiniciando servicios DHCP (IPv4 e IPv6)...")
    run_interactive("sudo systemctl restart isc-dhcp-server")
    run_interactive("sudo systemctl restart isc-dhcp-server6")

    print("[✓] Archivos DHCP creados y servicios reiniciados exitosamente en /etc/dhcp/.")
    print("[*] Esperando 15 segundos...")
    time.sleep(15)

    mark_step_completed("provisional_dhcp")

def reinstall_goss():
    if is_step_completed("reinstall_goss"):
        print("[=] Paso 'reinstall_goss' ya fue ejecutado previamente. Omitiendo...")
        return

    print("--- PASO 9.5: Limpieza y Reinstalacion de Goss ---")

    print("[*] Limpiando archivos goss anteriores...")
    run_command("rm -f goss*", check=False)

    print("[*] Instalando Goss de forma automatizada...")
    goss_install_cmd = "curl -fsSL https://goss.rocks/install | sudo sh"
    run_interactive(goss_install_cmd)

    print("[✓] Goss reinstalado exitosamente.")
    mark_step_completed("reinstall_goss")

def run_final_abmx_config():
    if is_step_completed("run_final_abmx_config"):
        print("[=] Paso 'run_final_abmx_config' ya fue ejecutado previamente. Omitiendo...")
        return

    print("--- PASO 10: Run Final ABMX Server Configuration via Git-Mirror ---")
    state = load_state()
    ip_address = state.get("config", {}).get("ip_address")

    if not ip_address:
        raise RuntimeError("No se encontro la IP en la configuracion. Asegurate de correr 'set_ID' primero.")

    sudo_user = os.environ.get('SUDO_USER', 'testusr')

    print("[*] Corrigiendo ownership de /home/testusr/.local...")
    fix_local_dir_cmd = f"sudo chown -R {sudo_user}:{sudo_user} /home/{sudo_user}/.local"
    run_interactive(fix_local_dir_cmd)

    mirror_ip = "172.24.125.2"

    ssh_copy_cmd = f"ssh-copy-id -i ~/.ssh/id_rsa.pub {sudo_user}@{ip_address}"
    cmd_remote_copy = f"ssh {sudo_user}@{mirror_ip} '{ssh_copy_cmd}'"
    print(f"[CMD Interactive] {cmd_remote_copy}")

    child_copy = pexpect.spawn("bash", ["-c", cmd_remote_copy], encoding="utf-8", timeout=300)
    child_copy.logfile_read = sys.stdout

    while True:
        idx = child_copy.expect([
            r"Are you sure you want to continue connecting \(yes/no/\[fingerprint\]\)\?",
            r"testusr@172\.24\.125\.2's password:",
            r"[pP]assword:",
            pexpect.EOF,
            pexpect.TIMEOUT
        ], timeout=120)

        if idx == 0:
            child_copy.sendline("yes")
        elif idx in (1, 2):
            child_copy.sendline(MIRROR_PASSWORD)
        elif idx == 3:
            break
        elif idx == 4:
            child_copy.close()
            raise RuntimeError("Timeout intentando ssh-copy-id desde el Git-Mirror.")

    child_copy.close()

    ansible_cmd = (
        f"cd ~/amp-ansible && ansible-playbook -i {ip_address}, repo_updater/configure-fish-station.yaml "
        f"-vv --ask-become-pass --ask-pass --flush-cache --vault-id @prompt"
    )
    cmd_remote_ansible = f"ssh -t {sudo_user}@{mirror_ip} '{ansible_cmd}'"
    print(f"[CMD Interactive] {cmd_remote_ansible}")

    child_ansible = pexpect.spawn("bash", ["-c", cmd_remote_ansible], encoding="utf-8", timeout=None)
    child_ansible.logfile_read = sys.stdout

    play_recap_detected = False

    while True:
        idx = child_ansible.expect([
            r"Are you sure you want to continue connecting \(yes/no/\[fingerprint\]\)\?",
            r"testusr@172\.24\.125\.2's password:",
            r"SSH password:",
            r"BECOME password\[defaults to SSH password\]:",
            r"BECOME password:",
            r"Vault password \(default\):",
            r"Please enter the password for 'testusr' \(operator\)",
            r"\[sudo\] password for testusr:",
            r"PLAY RECAP",
            pexpect.EOF
        ], timeout=None)

        if idx == 0:
            child_ansible.sendline("yes")
        elif idx == 1:
            child_ansible.sendline(MIRROR_PASSWORD)
        elif idx in (2, 3, 4, 6, 7):
            child_ansible.sendline(SUDO_PASSWORD)
        elif idx == 5:
            child_ansible.sendline(VAULT_PASSWORD)
        elif idx == 8:
            play_recap_detected = True
            child_ansible.sendline("exit")
        elif idx == 9:
            break

    child_ansible.close()

    print("[*] Reactivando sudo de forma automatica tras salir del mirror...")
    _activate_sudo()

    if not play_recap_detected or child_ansible.exitstatus != 0:
        print_ascii_fail()
        raise RuntimeError(f"Error en ejecucion de ansible-playbook via git-mirror (Exit code: {child_ansible.exitstatus})")

    mark_step_completed("run_final_abmx_config")
    print("[*] Esperando 15 segundos antes de finalizar el paso...")
    time.sleep(15)

def create_networkmanager_symlink():
    if is_step_completed("create_networkmanager_symlink"):
        print("[=] Paso 'create_networkmanager_symlink' ya fue ejecutado previamente. Omitiendo...")
        return

    print("--- PASO 11: Create NetworkManager Symlink & Install Required Packages ---")
    target_dir = "/usr/lib/systemd/system"

    print(f"[*] Listando archivos *etwork* en {target_dir}:")
    run_command(f"ls -l {target_dir}/*etwork*", check=False)

    print("[*] Actualizando lista de paquetes e instalando libsss-sudo y gnome-control-center...")
    apt_install(["libsss-sudo", "gnome-control-center"])

    print("[*] Creando symlink para network-manager.service...")
    symlink_cmd = f"sudo ln -sf {target_dir}/NetworkManager.service {target_dir}/network-manager.service"
    run_interactive(symlink_cmd)

    print("[*] Recargando daemon de systemd...")
    run_interactive("sudo systemctl daemon-reload")

    mark_step_completed("create_networkmanager_symlink")

def network_plan():
    if is_step_completed("network_plan"):
        print("[=] Paso 'network_plan' ya fue ejecutado previamente. Omitiendo...")
        return

    print("--- PASO 12: Configure Netplan for ens4f0 & ens4f1 ---")

    mac_f0 = None
    mac_f1 = None

    try:
        path_f0 = '/sys/class/net/ens4f0/address'
        path_f1 = '/sys/class/net/ens4f1/address'
        
        if os.path.exists(path_f0):
            with open(path_f0, 'r') as f:
                mac_f0 = f.read().strip().lower()
        if os.path.exists(path_f1):
            with open(path_f1, 'r') as f:
                mac_f1 = f.read().strip().lower()
    except Exception as e:
        print(f"[!] Warning leyendo sysfs: {e}")

    if not mac_f0 or not mac_f1:
        raw_output = run_command("ifconfig", check=False)
        
        if isinstance(raw_output, (tuple, list)):
            ifconfig_str = str(raw_output[0])
        elif isinstance(raw_output, bytes):
            ifconfig_str = raw_output.decode('utf-8', errors='ignore')
        else:
            ifconfig_str = str(raw_output)

        if not mac_f0:
            f0_match = re.search(r'ens4f0:.*?\bether\s+([0-9a-fA-F:]{17})', ifconfig_str, re.DOTALL)
            if f0_match:
                mac_f0 = f0_match.group(1).lower()

        if not mac_f1:
            f1_match = re.search(r'ens4f1:.*?\bether\s+([0-9a-fA-F:]{17})', ifconfig_str, re.DOTALL)
            if f1_match:
                mac_f1 = f1_match.group(1).lower()

    if not mac_f0 or not mac_f1:
        print_ascii_fail()
        raise RuntimeError(f"No se pudieron obtener las direcciones MAC (ens4f0: {mac_f0}, ens4f1: {mac_f1})")

    print(f"[+] MAC ens4f0: {mac_f0}")
    print(f"[+] MAC ens4f1: {mac_f1}")

    state = load_state()
    if "interfaces" not in state:
        state["interfaces"] = {}

    state["interfaces"]["ens4f0"] = mac_f0
    state["interfaces"]["ens4f1"] = mac_f1
    save_state(state)

    netplan_content = f"""# Let NetworkManager manage all devices on this system
network:
  version: 2
  ethernets:
      ens4f0np0:
               dhcp4: no
               match:
                   macaddress: {mac_f0}
               set-name: ens4f0
      ens4f1np1:
               dhcp4: no
               match:
                   macaddress: {mac_f1}
               set-name: ens4f1
  renderer: NetworkManager
"""

    netplan_path = "/etc/netplan/01-network-manager-all.yaml"
    temp_netplan = "/tmp/01-network-manager-all.yaml"

    print(f"[*] Actualizando {netplan_path}...")
    with open(temp_netplan, "w") as f:
        f.write(netplan_content)

    run_interactive(f"sudo mv {temp_netplan} {netplan_path}")
    run_interactive(f"sudo chmod 600 {netplan_path}")

    print("[*] Aplicando Netplan...")
    run_interactive("sudo netplan try --timeout 5")
    run_interactive("sudo netplan apply")

    mark_step_completed("network_plan")

def force_test_network_selection():

    print("--- PASO: Forzar seleccion de 'Test Network' en Ethernet (ens4f0) ---")

    interface = "ens4f0"
    target_conn = "Test Network"

    print(f"[*] Consultando perfiles de NetworkManager asociados a {interface}...")
    result = subprocess.run(
        ["nmcli", "-t", "-f", "NAME,DEVICE,UUID", "connection", "show"],
        capture_output=True, text=True
    )

    if result.returncode != 0:
        print_ascii_fail()
        raise RuntimeError(f"No se pudo consultar las conexiones de NetworkManager: {result.stderr.strip()}")

    profiles_on_iface = []
    for line in result.stdout.strip().splitlines():
        parts = line.split(":")
        if len(parts) < 3:
            continue
        name, device = parts[0], parts[1]
        if device == interface:
            profiles_on_iface.append(name)

    print(f"[+] Perfiles detectados en {interface}: {profiles_on_iface or 'ninguno activo actualmente'}")

    all_names = subprocess.run(
        ["nmcli", "-t", "-f", "NAME", "connection", "show"],
        capture_output=True, text=True
    ).stdout.splitlines()

    if target_conn not in all_names:
        print_ascii_fail()
        raise RuntimeError(
            f"El perfil '{target_conn}' no existe en NetworkManager. "
            f"Debe crearse antes de poder forzar su seleccion."
        )

    print(f"[*] Activando el perfil '{target_conn}' en {interface}...")
    run_interactive(f'sudo nmcli connection up id "{target_conn}" ifname {interface}')

    print(f"[*] Asignando autoconexion y prioridad alta a '{target_conn}'...")
    run_interactive(
        f'sudo nmcli connection modify "{target_conn}" '
        f'connection.autoconnect yes connection.autoconnect-priority 100'
    )

    print(f"[*] Despriorizando otros perfiles detectados en {interface}...")
    for name in profiles_on_iface:
        if name == target_conn:
            continue
        print(f"    [-] Despriorizando perfil '{name}'...")
        run_interactive(f'sudo nmcli connection modify "{name}" connection.autoconnect-priority -100')

    print(f"[*] Verificando que '{target_conn}' quedo como conexion activa en {interface}...")
    verify = subprocess.run(
        ["nmcli", "-t", "-f", "GENERAL.CONNECTION", "device", "show", interface],
        capture_output=True, text=True
    )
    active_conn = verify.stdout.strip().split(":", 1)[-1].strip() if verify.stdout else ""

    if active_conn != target_conn:
        print_ascii_fail()
        raise RuntimeError(
            f"La conexion activa en {interface} es '{active_conn}', se esperaba '{target_conn}'."
        )

    print(f"[✓] '{target_conn}' quedo forzada como conexion activa en {interface}.")
    mark_step_completed("force_test_network_selection")

def _print_yellow_banner(message):
    YELLOW = "\033[93m\033[1m"
    RESET = "\033[0m"
    border = "=" * 80
    print(f"\n{YELLOW}{border}")
    print(f"[!] {message}")
    print(f"{border}{RESET}\n")

def _print_green_banner(message):
    GREEN = "\033[92m\033[1m"
    RESET = "\033[0m"
    border = "=" * 80
    print(f"\n{GREEN}{border}")
    print(f"[✓] {message}")
    print(f"{border}{RESET}\n")

def _try_minicom_connect(device, baud):
    cmd = f"sudo minicom -D {device} -b {baud}"
    print(f"[CMD Interactive] {cmd}")
    c = pexpect.spawn("bash", ["-c", cmd], encoding="utf-8", timeout=30)
    c.logfile_read = sys.stdout

    idx = c.expect([
        r"\[sudo\] password for .*:?",
        r"[pP]assword:",
        r"Cannot open|No such file or directory|Device or resource busy|does not exist",
        r"Welcome to minicom|Press CTRL-A Z for help",
        pexpect.EOF,
        pexpect.TIMEOUT
    ], timeout=20)

    if idx in (0, 1):
        c.sendline(SUDO_PASSWORD)
        idx2 = c.expect([
            r"Cannot open|No such file or directory|Device or resource busy|does not exist",
            r"Welcome to minicom|Press CTRL-A Z for help",
            pexpect.EOF,
            pexpect.TIMEOUT
        ], timeout=20)
        if idx2 == 1:
            return c
        c.close(force=True)
        return None
    elif idx == 3:
        return c
    else:
        c.close(force=True)
        return None

def _wait_for_console_connection(banner_message, devices, baud):
    while True:
        available = [d for d in devices if os.path.exists(d)]

        if not available:
            _print_yellow_banner(banner_message)
            print("[*] Cable de consola no detectado aun. Reintentando en 3 segundos...")
            time.sleep(3)
            continue

        for device in available:
            child = _try_minicom_connect(device, baud)
            if child:
                print(f"[✓] Conexion via minicom establecida en {device}")
                return child, device

        print("[!] Se detecto el dispositivo pero no se pudo abrir minicom. Reintentando en 3 segundos...")
        time.sleep(3)

def _wait_for_console_connection_enter(banner_message, devices, baud):
    while True:
        _print_yellow_banner(banner_message)
        input("Conecte el cable de consola y presione ENTER para continuar...")

        available = [d for d in devices if os.path.exists(d)]

        if not available:
            print("[!] Cable de consola no detectado. Verifique la conexion e intente nuevamente.")
            continue

        for device in available:
            child = _try_minicom_connect(device, baud)
            if child:
                print(f"[✓] Conexion via minicom establecida en {device}")
                return child, device

        print("[!] Se detecto el dispositivo pero no se pudo abrir minicom. Intente nuevamente.")

def _minicom_exit(child):
    if child is None or getattr(child, "closed", False):
        return
    print("[*] Saliendo de minicom (Ctrl+A, X)...")
    try:
        child.send(chr(1))
        time.sleep(0.5)
        child.send("x")
        idx = child.expect(
            [r"Leave Minicom\?", pexpect.TIMEOUT, pexpect.EOF],
            timeout=15
        )
        if idx == 0:
            child.sendline("")
    except Exception as e:
        print(f"[!] Advertencia: no se pudo confirmar la salida limpia de minicom ({e}).")
    finally:
        try:
            child.close(force=True)
        except Exception:
            pass
        os.system("clear")

def _juniper_expect_or_fail(child, patterns, timeout, error_msg):
    full_patterns = list(patterns) + [pexpect.TIMEOUT, pexpect.EOF]
    idx = child.expect(full_patterns, timeout=timeout)
    if idx >= len(patterns):
        print_ascii_fail()
        raise RuntimeError(error_msg)
    return idx

def juniper_config():
    if is_step_completed("juniper_config"):
        print("[=] Paso 'juniper_config' ya fue ejecutado previamente. Omitiendo...")
        return

    print("--- PASO: Configuracion Automatica del Juniper via Consola Serial ---")

    mensaje = (
        "Conecte cable consola al puerto CON del Juniper (Por la parte de atras) "
        "y el otro extremo a un puerto USB 3.0 del Superlogics/ABMX."
    )

    child, used_device = _wait_for_console_connection_enter(mensaje, ["/dev/ttyUSB0", "/dev/ttyUSB1"], 9600)
    child.logfile_read = sys.stdout

    try:

        print("[*] Buscando prompt de login del Juniper...")
        child.sendline("")
        idx = _juniper_expect_or_fail(
            child,
            [r"login:", r"root@.*[%>#]\s"],
            timeout=20,
            error_msg="No se detecto el prompt 'login:' del Juniper tras conectar por consola."
        )

        if idx == 0:
            print("[*] Prompt 'login:' detectado. Ingresando usuario 'root'...")
            child.sendline("root")

            print("[*] Validando version de JUNOS...")
            idx_auth = child.expect([
                r"Password:",
                r"JUNOS 20\.2R2\.11 Kernel 64-bit FLEX JNPR-11\.0",
                pexpect.TIMEOUT,
                pexpect.EOF
            ], timeout=20)

            if idx_auth == 0:
                print("[=] El Juniper solicito 'Password:' tras ingresar 'root': "
                      "esto indica que ya se encuentra configurado.")
                _minicom_exit(child)
                _print_green_banner(
                    "EL JUNIPER YA ESTABA CONFIGURADO. Se omite el resto de los "
                    "pasos de configuracion automatica para este equipo."
                )
                mark_step_completed(
                    "juniper_config",
                    {"juniper_console_device": used_device, "juniper_already_configured": True}
                )
                return
            elif idx_auth in (2, 3):
                print_ascii_fail()
                raise RuntimeError(
                    "No se detecto ni el prompt 'Password:' ni la version esperada de "
                    "JUNOS tras ingresar el usuario 'root'."
                )
        else:
            print("[=] La sesion ya se encontraba autenticada en el Juniper.")

            print("[*] Validando version de JUNOS...")
            idx_auth = child.expect([
                r"JUNOS 20\.2R2\.11 Kernel 64-bit FLEX JNPR-11\.0",
                pexpect.TIMEOUT,
                pexpect.EOF
            ], timeout=20)
            idx_auth = 1 if idx_auth == 0 else idx_auth + 1

        if idx_auth != 1:
            RED = "\033[91m\033[1m"
            RESET = "\033[0m"
            print(f"\n{RED}Version JUNIPER Incorrecta!!! Realizar Downgrade de Juniper...{RESET}\n")

            downgrade_msg = (
                "###Downgrade Juniper\n"
                "#Conecte cable consola a Juniper\n"
                "sudo apt install putty\n"
                "sudo putty -serial /dev/ttyUSB0 -sercfg 9600,8,n,1,N\n"
                "#si da error la USB0 cambiar por USB1\n"
                "#Coloque memoria usb con la imagen del juniper\n"
                "shutdown -r now\n"
                "#Mantenga latecla ESC presionada\n"
                "#dentro del bios de la juniper seleccione BOOT MANAGER\n"
                "#Seleccione la usb con laimagen\n"
                "#Instale la imagen"
            )
            _print_yellow_banner(downgrade_msg)

            input("Presione enter para continuar...")

            print_ascii_fail()
            print("[!] Cerrando gf_provisioning.py para realizar el downgrade manual del Juniper.")
            sys.exit(1)

        print("[✓] Version de JUNOS validada correctamente.")

        _juniper_expect_or_fail(
            child,
            [r"%\s"],
            timeout=20,
            error_msg="No se detecto el prompt de shell ('%') del Juniper tras el login."
        )

        print("[*] Entrando al CLI del Juniper...")
        child.sendline("cli")
        _juniper_expect_or_fail(
            child, [r">\s"], timeout=20,
            error_msg="No se detecto el prompt operacional ('>') tras ejecutar 'cli'."
        )

        child.sendline("configure")
        _juniper_expect_or_fail(
            child, [r"#\s"], timeout=20,
            error_msg="No se detecto el prompt de configuracion ('#') tras ejecutar 'configure'."
        )

        print("[*] Configurando root-authentication plain-text-password...")
        child.sendline("set system root-authentication plain-text-password")
        _juniper_expect_or_fail(
            child, [r"[Nn]ew password:"], timeout=20,
            error_msg="No se recibio el prompt 'New password:' de JUNOS."
        )
        child.sendline("google123")
        _juniper_expect_or_fail(
            child, [r"[Rr]etype new password:"], timeout=20,
            error_msg="No se recibio el prompt 'Retype new password:' de JUNOS."
        )
        child.sendline("google123")
        _juniper_expect_or_fail(
            child, [r"#\s"], timeout=20,
            error_msg="No se regreso al prompt de configuracion tras fijar la contrasena de root."
        )

        print("[*] Ejecutando commit (root-authentication)...")
        child.sendline("commit")
        _juniper_expect_or_fail(
            child, [r"commit complete"], timeout=60,
            error_msg="El 'commit' de root-authentication no reporto 'commit complete'."
        )

        print("[*] Eliminando chassis auto-image-upgrade...")
        child.sendline("delete chassis auto-image-upgrade")
        _juniper_expect_or_fail(
            child, [r"#\s"], timeout=20,
            error_msg="No se regreso al prompt de configuracion tras 'delete chassis auto-image-upgrade'."
        )

        child.sendline("commit")
        _juniper_expect_or_fail(
            child, [r"commit complete"], timeout=60,
            error_msg="El 'commit' de 'delete chassis auto-image-upgrade' no reporto 'commit complete'."
        )

        wildcard_commands = [
            "wildcard range delete interfaces et-0/0/[0-31] unit 0 family inet",
            "wildcard range delete interfaces et-0/0/[0-31]:[0-3] unit 0 family inet",
            "wildcard range delete interfaces xe-0/0/[0-31]:[0-3] unit 0 family inet",
            "wildcard range delete interfaces et-0/0/[0-31] unit 0",
            "wildcard range delete interfaces et-0/0/[0-31]:[0-3] unit 0",
            "wildcard range delete interfaces xe-0/0/[0-31]:[0-3] unit 0",
            "wildcard range set interfaces et-0/0/[0-31] unit 0 family ethernet-switching",
            "wildcard range set interfaces xe-0/0/[0-31]:[0-3] unit 0 family ethernet-switching",
        ]
        print("[*] Ejecutando comandos 'wildcard range' sobre las interfaces...")
        for wc_cmd in wildcard_commands:
            child.sendline(wc_cmd)
            _juniper_expect_or_fail(
                child, [r"#\s"], timeout=30,
                error_msg=f"No se regreso al prompt de configuracion tras: '{wc_cmd}'."
            )

        print("[*] Ejecutando commit final de interfaces...")
        child.sendline("commit")
        _juniper_expect_or_fail(
            child, [r"commit complete"], timeout=60,
            error_msg="El 'commit' final de interfaces no reporto 'commit complete'."
        )

        child.sendline("exit")
        _juniper_expect_or_fail(
            child, [r">\s"], timeout=20,
            error_msg="No se regreso al modo operacional ('>') tras 'exit' de configure."
        )

        print("[*] Revisando alarmas del sistema (antes de rescue save)...")
        child.sendline("show system alarms")
        _juniper_expect_or_fail(
            child, [r">\s"], timeout=20,
            error_msg="No se recibio respuesta de 'show system alarms'."
        )

        print("[*] Guardando configuracion de rescate (rescue save)...")
        child.sendline("request system configuration rescue save")
        _juniper_expect_or_fail(
            child, [r">\s"], timeout=30,
            error_msg="No se recibio confirmacion de 'request system configuration rescue save'."
        )

        print("[*] Revisando alarmas del sistema (despues de rescue save)...")
        child.sendline("show system alarms")
        _juniper_expect_or_fail(
            child, [r">\s"], timeout=20,
            error_msg="No se recibio respuesta de 'show system alarms' (segunda revision)."
        )

        print("[*] Saliendo del CLI de JUNOS...")
        child.sendline("exit")
        _juniper_expect_or_fail(
            child, [r"%\s", r"login:"], timeout=20,
            error_msg="No se regreso al prompt de shell tras salir del CLI."
        )

        print("[*] Ejecutando 'shutdown -r now' para reiniciar el Juniper...")
        child.sendline("shutdown -r now")
        time.sleep(5)

    finally:
        _minicom_exit(child)

    _print_green_banner("CONFIGURACION DEL JUNIPER COMPLETADA EXITOSAMENTE.")
    mark_step_completed("juniper_config", {"juniper_console_device": used_device})

def zpe_config():
    if is_step_completed("zpe_config"):
        print("[=] Paso 'zpe_config' ya fue ejecutado previamente. Omitiendo...")
        return

    print("--- PASO: Configuracion Automatica del ZPE via Consola Serial ---")

    mensaje = (
        "Conecte cable consola al puerto CONSOLE del ZPE y el otro extremo "
        "a un puerto USB 3.0 del Superlogics/ABMX."
    )

    child, used_device = _wait_for_console_connection_enter(mensaje, ["/dev/ttyUSB0", "/dev/ttyUSB1"], 115200)
    child.logfile_read = sys.stdout

    zpe_mac = None
    already_configured = False

    try:
        print("[*] Buscando prompt de login del ZPE...")
        child.sendline("")
        idx = child.expect([
            r"nodegrid login:",
            r"[Uu]ser(name)?:",
            r"\[admin@nodegrid[^\]]*\]#\s",
            pexpect.TIMEOUT,
            pexpect.EOF
        ], timeout=20)

        if idx == 0:
            print("[=] Se detecto el prompt 'nodegrid login:': "
                  "esto indica que el ZPE ya se encuentra configurado.")
            already_configured = True
            print("[*] Enviando usuario 'admin' para extraer la MAC...")
            child.sendline("admin")
            idx2 = child.expect([r"[Pp]ass(word)?:", pexpect.TIMEOUT, pexpect.EOF], timeout=20)
            if idx2 != 0:
                print_ascii_fail()
                raise RuntimeError("No se recibio el prompt 'password:' del ZPE tras enviar el usuario.")
            print("[*] Prompt 'password:' detectado. Enviando password 'admin'...")
            child.sendline("admin")
            idx3 = child.expect([r"#\s", pexpect.TIMEOUT, pexpect.EOF], timeout=20)
            if idx3 != 0:
                print_ascii_fail()
                raise RuntimeError("No se recibio el prompt de shell ('#') del ZPE tras el login.")
        elif idx == 1:
            print("[*] Prompt 'user:' detectado. Enviando usuario 'admin'...")
            child.sendline("admin")
            idx2 = child.expect([r"[Pp]ass(word)?:", pexpect.TIMEOUT, pexpect.EOF], timeout=20)
            if idx2 != 0:
                print_ascii_fail()
                raise RuntimeError("No se recibio el prompt 'password:' del ZPE tras enviar el usuario.")
            print("[*] Prompt 'password:' detectado. Enviando password 'admin'...")
            child.sendline("admin")
            idx3 = child.expect([r"#\s", pexpect.TIMEOUT, pexpect.EOF], timeout=20)
            if idx3 != 0:
                print_ascii_fail()
                raise RuntimeError("No se recibio el prompt de shell ('#') del ZPE tras el login.")
        elif idx == 2:
            print("[=] La sesion ya se encontraba autenticada en el ZPE.")
        else:
            print_ascii_fail()
            raise RuntimeError("No se detecto el prompt 'user:' del ZPE tras conectar por consola.")

        print("[✓] Login en el ZPE completado.")

        print("[*] Consultando /settings/network_connections...")
        child.sendline("cd /settings/network_connections")
        idx = child.expect([r"#\s", pexpect.TIMEOUT, pexpect.EOF], timeout=20)
        if idx != 0:
            print_ascii_fail()
            raise RuntimeError("No se pudo entrar a /settings/network_connections en el ZPE.")

        child.sendline("show")
        idx = child.expect([r"#\s", pexpect.TIMEOUT, pexpect.EOF], timeout=45)
        if idx != 0:
            print_ascii_fail()
            raise RuntimeError("No se recibio la salida del comando 'show' en el ZPE.")

        show_output = child.before

        eth1_idx = show_output.find("ETH1")
        if eth1_idx == -1:
            print_ascii_fail()
            raise RuntimeError("No se encontro la seccion 'ETH1' en la salida de 'show' del ZPE.")

        section = show_output[eth1_idx:]
        next_eth_idx = section.find("ETH", 4)
        next_hotspot_idx = section.find("hotspot")
        end_candidates = [i for i in (next_eth_idx, next_hotspot_idx) if i != -1]
        section = section[:min(end_candidates)] if end_candidates else section

        mac_matches = re.findall(r'([0-9a-fA-F]{2}(?::[0-9a-fA-F]{2}){5})', section)
        if not mac_matches:
            print_ascii_fail()
            raise RuntimeError("No se pudo extraer la direccion MAC de ETH1 en la salida del ZPE.")

        zpe_mac = mac_matches[0].lower()
        print(f"[+] MAC ETH1 (ZPE) detectada: {zpe_mac}")

    finally:
        _minicom_exit(child)

    mark_step_completed("zpe_config", {"zpe_console_device": used_device, "zpe_mac": zpe_mac, "zpe_already_configured": already_configured})

    print("[*] Actualizando /etc/dhcp/dhcpd.conf con la MAC real del ZPE...")
    new_line = f"host zpe {{ hardware ethernet {zpe_mac}; fixed-address 10.0.0.253; }}"
    sed_cmd = (
        "sudo sed -i '/host zpe { hardware ethernet/c\\"
        f"{new_line}' /etc/dhcp/dhcpd.conf"
    )
    run_interactive(sed_cmd)

    print("[*] Verificando que la MAC se haya aplicado correctamente...")
    run_interactive(f"sudo grep -q '{zpe_mac}' /etc/dhcp/dhcpd.conf")

    print("[*] Reiniciando servicios DHCP (IPv4 e IPv6)...")
    run_interactive("sudo systemctl restart isc-dhcp-server")
    run_interactive("sudo systemctl restart isc-dhcp-server6")

    if already_configured:
        _print_green_banner(
            "EL ZPE YA ESTABA CONFIGURADO. Se extrajo la MAC y se actualizó el DHCP, "
            "omitiendo la ejecución del script de configuración de puertos por SSH."
        )
        return

    sudo_user = os.environ.get('SUDO_USER', 'testusr')
    zpe_script_dir = f"/home/{sudo_user}/lego-infra/lego_setup/lego_zpe_console_server"
    ssh_cmd = (
        f"cd {zpe_script_dir} && "
        "ssh -t -t -v -o ConnectTimeout=10 admin@10.0.0.253 < lego_config_zpe_allports.sh"
    )
    print(f"[CMD Interactive] {ssh_cmd}")
    ssh_child = pexpect.spawn("bash", ["-c", ssh_cmd], encoding="utf-8", timeout=600)
    ssh_child.logfile_read = sys.stdout

    idx = ssh_child.expect([
        r"\(admin@10\.0\.0\.253\)\s*Password:",
        pexpect.EOF,
        pexpect.TIMEOUT
    ], timeout=60)

    if idx == 0:
        print("[*] Prompt de password SSH detectado. Enviando password 'admin'...")
        ssh_child.sendline("admin")
        idx2 = ssh_child.expect([pexpect.EOF, pexpect.TIMEOUT], timeout=540)
        if idx2 != 0:
            print_ascii_fail()
            ssh_child.close(force=True)
            raise RuntimeError("Timeout esperando que finalice lego_config_zpe_allports.sh via SSH.")
    elif idx == 1:
        print("[=] La sesion SSH finalizo sin solicitar password (posible autenticacion por llave).")
    else:
        print_ascii_fail()
        ssh_child.close(force=True)
        raise RuntimeError("Timeout esperando el prompt de password SSH hacia el ZPE (10.0.0.253).")

    ssh_child.close()
    if ssh_child.exitstatus not in (0, None):
        print_ascii_fail()
        raise RuntimeError(
            f"Error ejecutando lego_config_zpe_allports.sh via SSH (Exit code: {ssh_child.exitstatus})"
        )

    _print_green_banner("CONFIGURACION DEL ZPE COMPLETADA EXITOSAMENTE.")
    
def _scp_download_once(remote_user, remote_host, remote_path, destination="."):
    cmd = f"scp -r {remote_user}@{remote_host}:{remote_path} {destination}"
    print(f"[CMD Interactive] {cmd}")

    child = pexpect.spawn("bash", ["-c", cmd], encoding="utf-8", timeout=None)
    child.logfile_read = sys.stdout

    while True:
        idx = child.expect([
            r"Are you sure you want to continue connecting",
            r"[pP]assword:",
            pexpect.EOF,
            pexpect.TIMEOUT
        ], timeout=600)

        if idx == 0:
            child.sendline("yes")
        elif idx == 1:
            child.sendline(SUDO_PASSWORD)
        elif idx == 2:
            break
        elif idx == 3:
            child.close(force=True)
            raise RuntimeError(f"Timeout copiando '{remote_path}' desde {remote_host}.")

    child.close()
    if child.exitstatus != 0:
        raise RuntimeError(
            f"Error copiando '{remote_path}' desde {remote_host} (Exit code: {child.exitstatus})."
        )

def _scp_download(remote_user, remote_host, remote_path, destination="."):
    try:
        _retry_download(
            lambda: _scp_download_once(remote_user, remote_host, remote_path, destination),
            f"SCP de '{remote_path}' desde {remote_host}"
        )
    except RuntimeError:
        print_ascii_fail(f"No se pudo copiar '{remote_path}' desde {remote_host}.")
        raise

def _run_shell_sequence(commands, timeout=600):
    print("[*] Ejecutando secuencia de comandos (sesion de shell persistente):")
    for c in commands:
        print(f"    $ {c}")

    child = pexpect.spawn("bash", encoding="utf-8", timeout=timeout)
    child.logfile_read = sys.stdout

    try:
        for cmd in commands:
            marker = f"__CMDDONE_{uuid.uuid4().hex}__"
            child.sendline(f"{cmd}; echo {marker}$?")

            exit_code = None
            while exit_code is None:
                idx = child.expect([
                    rf"{marker}(\d+)",
                    r"\[sudo\] password for .*:?",
                    r"[pP]assword:",
                    pexpect.TIMEOUT,
                    pexpect.EOF
                ], timeout=timeout)

                if idx == 0:
                    exit_code = int(child.match.group(1))
                elif idx in (1, 2):
                    child.sendline(SUDO_PASSWORD)
                else:
                    print_ascii_fail()
                    raise RuntimeError(f"Timeout/EOF ejecutando '{cmd}' en la secuencia de shell.")

            if exit_code != 0:
                print_ascii_fail()
                raise RuntimeError(f"El comando '{cmd}' fallo con codigo de salida {exit_code}.")
    finally:
        try:
            child.sendline("exit")
            child.close(force=True)
        except Exception:
            pass

def vrmu_util_config():
    if is_step_completed("vrmu_util_config"):
        print("[=] Paso 'vrmu_util_config' ya fue ejecutado previamente. Omitiendo...")
        return

    print("--- PASO: Descarga y configuracion de VRMU Util / Viperfish-DVC ---")

    remote_host = "172.24.125.172"
    sudo_user = os.environ.get('SUDO_USER', 'testusr')
    remote_user = sudo_user
    home_dir = f"/home/{sudo_user}"

    items_to_download = [
        "viperfish-dvc",
        "vrmu_util",
        "ledare_1_*",
        "FWContainer_EN_3_AP_00_02_00_09.bin",
    ]

    for item in items_to_download:
        remote_path = f"/home/{remote_user}/{item}"
        print(f"[*] Descargando '{item}' desde {remote_host}...")
        _scp_download(remote_user, remote_host, remote_path, destination=".")

    print("[*] Copiando imagen 'tross' a /tftpboot/...")
    _run_shell_sequence([
        "cd viperfish-dvc/vin-sweep/",
        "sudo cp -r tross /tftpboot/",
    ])

    print("[*] Copiando vrmu_util al home y asignando permisos...")

    downloaded_vrmu_path = os.path.abspath("vrmu_util")
    home_vrmu_path = os.path.join(home_dir, "vrmu_util")

    if (os.path.exists(downloaded_vrmu_path) and os.path.exists(home_vrmu_path)
            and os.path.samefile(downloaded_vrmu_path, home_vrmu_path)):
        print("[=] 'vrmu_util' ya se encuentra en el home del usuario. Omitiendo la copia, solo se ajustan permisos...")
        _run_shell_sequence([
            "cd",
            "chmod 777 vrmu_util",
        ])
    else:
        _run_shell_sequence([
            "cd",
            "cp vrmu_util ~",
            "chmod 777 vrmu_util",
        ])

    print("[✓] Configuracion de VRMU Util completada exitosamente.")
    mark_step_completed("vrmu_util_config")

def tross_capture_mac():
    if is_step_completed("tross_capture_mac"):
        print("[=] Paso 'tross_capture_mac' ya fue ejecutado previamente. Omitiendo...")
        return

    print("--- PASO: Captura de la MAC del Tross ---")

    _print_yellow_banner("Por favor, introduzca la direccion MAC del Tross.")
    mac_input = input("MAC del Tross: ").strip()

    clean_mac = re.sub(r'[^0-9a-fA-F]', '', mac_input)

    if len(clean_mac) != 12:
        print_ascii_fail()
        raise ValueError(
            f"La MAC ingresada no es valida (se esperaban 12 caracteres hexadecimales, "
            f"se obtuvieron {len(clean_mac)}): '{mac_input}'"
        )

    tross_mac = ":".join(clean_mac[i:i + 2] for i in range(0, 12, 2)).lower()
    print(f"[+] MAC normalizada del Tross: {tross_mac}")

    mark_step_completed("tross_capture_mac", {"tross_mac": tross_mac})

    print("[*] Actualizando /etc/dhcp/dhcpd.conf con la MAC real del Tross...")
    new_line = f"host tross {{ hardware ethernet {tross_mac}; fixed-address 10.0.0.251; }}"
    sed_cmd = (
        "sudo sed -i '/host tross { hardware ethernet/c\\"
        f"{new_line}' /etc/dhcp/dhcpd.conf"
    )
    run_interactive(sed_cmd)

    print("[*] Verificando que la MAC se haya aplicado correctamente...")
    run_interactive(f"sudo grep -q '{tross_mac}' /etc/dhcp/dhcpd.conf")

    print("[✓] MAC del Tross capturada y aplicada exitosamente.")


TROSS_PROMPT = r"root@[^:\r\n]*:[^\r\n]*"

UBOOT_PROMPT = r"\r\n=> $"

ZPE_READONLY_MARKER = "[read-only -- use ^X t ? for help]"

class _ZpeConsoleReadOnlyError(RuntimeError):
    pass

def _paced_sendline(child, line, delay=0.4):
    child.sendline(line)
    time.sleep(delay)

def _print_red_banner(message):
    RED = "\033[91m\033[1m"
    RESET = "\033[0m"
    border = "=" * 80
    print(f"\n{RED}{border}")
    for line in message.split("\n"):
        print(f"[!] {line}")
    print(f"{border}{RESET}\n")

def _green_wait(seconds, label="Esperando"):
    GREEN = "\033[92m"
    RESET = "\033[0m"
    print(f"[*] {label}: esperando {seconds}s...")
    start = time.time()
    while True:
        elapsed = int(time.time() - start)
        if elapsed >= seconds:
            break
        remaining = seconds - elapsed
        sys.stdout.write(f"\r{GREEN}[{label}] Tiempo restante: {remaining}s...{RESET}")
        sys.stdout.flush()
        time.sleep(1)
    sys.stdout.write(f"\r{GREEN}[{label}] Completado.{' ' * 20}{RESET}\n")

def _update_state_config(extra):
    state = load_state()
    state.setdefault("config", {}).update(extra)
    save_state(state)

def _mac_plus_offset(mac, offset):
    parts = mac.split(":")
    last = (int(parts[-1], 16) + offset) % 256
    parts[-1] = f"{last:02x}"
    return ":".join(parts)

def _zpe_console_take_control(child):
    print("[*] Tomando control de escritura de la consola (Ctrl-X, t)...")
    child.send(chr(0x18))
    time.sleep(0.3)
    child.send("t")
    time.sleep(0.3)

def _drain_buffered_output(child, idle_timeout=0.3):
    try:
        while True:
            child.read_nonblocking(size=65536, timeout=idle_timeout)
    except pexpect.exceptions.TIMEOUT:
        pass
    except pexpect.exceptions.EOF:
        pass

def _open_zpe_console_telnet(port, timeout=45, take_control=False):
    cmd = f"telnet 10.0.0.253 {port}"
    print(f"[CMD Interactive] {cmd}")
    child = pexpect.spawn("bash", ["-c", cmd], encoding="utf-8", timeout=timeout)
    child.logfile_read = sys.stdout
    idx = child.expect([r"Escape character is", pexpect.TIMEOUT, pexpect.EOF], timeout=20)
    if idx != 0:
        output = (child.before or "").strip()
        try:
            child.close(force=True)
        except Exception:
            pass
        print_ascii_fail(
            f"No se pudo conectar a la consola del ZPE (telnet 10.0.0.253 {port}). "
            f"Verifique que el ZPE este encendido y accesible en la red."
        )
        raise RuntimeError(
            f"No se pudo abrir la consola del ZPE (10.0.0.253:{port}): {output or 'sin respuesta'}"
        )
    if take_control:
        _zpe_console_take_control(child)
    _drain_buffered_output(child)
    return child

def _zpe_console_exit(child):
    if child is None or getattr(child, "closed", False):
        return
    print("[*] Saliendo de la consola relay del ZPE (Ctrl+5, q)...")
    try:
        child.send(chr(0x1D))
        time.sleep(0.5)
        child.sendline("q")
        child.expect([pexpect.EOF, pexpect.TIMEOUT], timeout=15)
    except Exception as e:
        print(f"[!] Advertencia: no se pudo confirmar la salida limpia de la consola del ZPE ({e}).")
    finally:
        try:
            child.close(force=True)
        except Exception:
            pass
        os.system("clear")

def _uboot_break_spam(child, max_seconds=180, spam_window=25):
    print("[*] Esperando (sin enviar teclas aun) el mensaje 'Hit any key to stop autoboot:' del Tross...")
    idx = child.expect([r"Hit any key to stop autoboot", pexpect.TIMEOUT, pexpect.EOF], timeout=max_seconds)
    if idx != 0:
        print_ascii_fail("No se recibio el mensaje 'Hit any key to stop autoboot:' del Tross.")
        raise RuntimeError("Timeout esperando 'Hit any key to stop autoboot:' en el Tross.")

    print("[✓] 'Hit any key to stop autoboot:' detectado. Probando teclas de interrupcion...")
    candidate_keys = ["\r", " "]
    deadline = time.time() + spam_window
    i = 0
    while time.time() < deadline:
        key = candidate_keys[i % len(candidate_keys)]
        i += 1
        child.send(key)
        idx = child.expect([UBOOT_PROMPT, pexpect.TIMEOUT, pexpect.EOF], timeout=0.2)
        if idx == 0:
            print("[✓] Prompt '=>' de U-Boot detectado.")
            return
        if idx == 2:
            print_ascii_fail(
                "La sesion de consola se cerro inesperadamente al intentar interrumpir el "
                "autoboot (posible tecla reservada por el gateway del ZPE)."
            )
            raise RuntimeError("EOF inesperado interrumpiendo el autoboot del Tross.")
        if ZPE_READONLY_MARKER in (child.before or ""):
            print_ascii_fail(
                "La consola del ZPE quedo en modo solo-lectura: ninguna tecla llega al Tross."
            )
            raise _ZpeConsoleReadOnlyError(
                "La consola relay del ZPE esta en modo solo-lectura (aviso "
                f"'{ZPE_READONLY_MARKER}' detectado)."
            )
    print_ascii_fail(
        "Se detecto 'Hit any key to stop autoboot:' pero no se logro interrumpir el "
        "arranque (nunca aparecio el prompt '=>')."
    )
    raise RuntimeError("No se pudo interrumpir el autoboot del Tross a tiempo.")

def _uboot_cmd_check(child, cmd, expected_substrings, timeout=45, fail_msg=None):
    if isinstance(expected_substrings, str):
        expected_substrings = [expected_substrings]
    print(f"[CMD U-Boot] {cmd}")
    _paced_sendline(child, cmd)
    idx = child.expect([UBOOT_PROMPT, pexpect.TIMEOUT, pexpect.EOF], timeout=timeout)
    output = child.before or ""
    if idx != 0 or not all(s in output for s in expected_substrings):
        print_ascii_fail(fail_msg or f"Respuesta inesperada del Tross tras el comando '{cmd}'.")
        raise RuntimeError(f"Fallo validando la respuesta de U-Boot para '{cmd}'.")
    print(f"[✓] Respuesta validada para '{cmd}'.")
    return output

def _wait_for_pattern_with_enters(child, pattern, max_seconds, interval=5, label="Esperando"):
    GREEN = "\033[92m"
    RESET = "\033[0m"
    elapsed = 0
    while elapsed < max_seconds:
        child.sendline("")
        idx = child.expect([pattern, pexpect.TIMEOUT, pexpect.EOF], timeout=interval)
        if idx == 0:
            sys.stdout.write(f"\r{GREEN}[{label}] Completado en {elapsed}s.{' ' * 20}{RESET}\n")
            return True
        if idx == 2:
            return False
        if ZPE_READONLY_MARKER in (child.before or ""):
            print_ascii_fail(
                "La consola del ZPE quedo en modo solo-lectura: ninguna tecla llega al Tross."
            )
            raise _ZpeConsoleReadOnlyError(
                "La consola relay del ZPE esta en modo solo-lectura (aviso "
                f"'{ZPE_READONLY_MARKER}' detectado)."
            )
        elapsed += interval
        sys.stdout.write(f"\r{GREEN}[{label}] Tiempo transcurrido: {elapsed}s (max {max_seconds}s)...{RESET}")
        sys.stdout.flush()
    sys.stdout.write(f"\r{GREEN}[{label}] Tiempo agotado tras {max_seconds}s.{' ' * 20}{RESET}\n")
    return False

def _wait_silently_for_pattern(child, pattern, max_seconds, poll_interval=5, label="Esperando"):
    GREEN = "\033[92m"
    RESET = "\033[0m"
    elapsed = 0
    while elapsed < max_seconds:
        idx = child.expect([pattern, pexpect.TIMEOUT, pexpect.EOF], timeout=poll_interval)
        if idx == 0:
            sys.stdout.write(f"\r{GREEN}[{label}] Completado en {elapsed}s.{' ' * 20}{RESET}\n")
            return True
        if idx == 2:
            return False
        elapsed += poll_interval
        sys.stdout.write(f"\r{GREEN}[{label}] Tiempo transcurrido: {elapsed}s (max {max_seconds}s)...{RESET}")
        sys.stdout.flush()
    sys.stdout.write(f"\r{GREEN}[{label}] Tiempo agotado tras {max_seconds}s.{' ' * 20}{RESET}\n")
    return False

def _run_tross_cmd_and_wait(child, cmd, max_wait_seconds, poll_interval=5, label="Esperando",
                             prompt_pattern=None):
    prompt_pattern = prompt_pattern or TROSS_PROMPT
    GREEN = "\033[92m"
    RESET = "\033[0m"
    print(f"[CMD Tross] {cmd}")
    _paced_sendline(child, cmd)
    elapsed = 0
    while True:
        idx = child.expect([prompt_pattern, pexpect.TIMEOUT, pexpect.EOF], timeout=poll_interval)
        if idx == 0:
            sys.stdout.write(f"\r{GREEN}[{label}] Completado en {elapsed}s.{' ' * 20}{RESET}\n")
            return child.before or ""
        if idx == 2:
            print_ascii_fail(f"La sesion del Tross se cerro inesperadamente durante '{cmd}'.")
            raise RuntimeError(f"EOF inesperado esperando la finalizacion de '{cmd}'.")
        if ZPE_READONLY_MARKER in (child.before or ""):
            print_ascii_fail(
                "La consola del ZPE quedo en modo solo-lectura: ninguna tecla llega al Tross."
            )
            raise _ZpeConsoleReadOnlyError(
                "La consola relay del ZPE esta en modo solo-lectura (aviso "
                f"'{ZPE_READONLY_MARKER}' detectado)."
            )
        elapsed += poll_interval
        sys.stdout.write(f"\r{GREEN}[{label}] Tiempo transcurrido: {elapsed}s (max {max_wait_seconds}s)...{RESET}")
        sys.stdout.flush()
        if elapsed >= max_wait_seconds:
            print_ascii_fail(f"Timeout esperando que finalice '{cmd}' en el Tross.")
            raise RuntimeError(f"Timeout ({max_wait_seconds}s) esperando la finalizacion de '{cmd}'.")

def _run_local_cmd_with_wait(cmd, max_wait_seconds, poll_interval=10, label="Esperando"):
    GREEN = "\033[92m"
    RESET = "\033[0m"
    marker = f"__CMDDONE_{uuid.uuid4().hex}__"
    print(f"[CMD Local] {cmd}")
    child = pexpect.spawn("bash", ["-c", f"{cmd}; echo {marker}$?"], encoding="utf-8",
                           timeout=max_wait_seconds + 60)
    child.logfile_read = sys.stdout
    elapsed = 0
    while True:
        idx = child.expect([rf"{marker}(\d+)", pexpect.TIMEOUT, pexpect.EOF], timeout=poll_interval)
        if idx == 0:
            exit_code = int(child.match.group(1))
            output = child.before or ""
            child.close(force=True)
            sys.stdout.write(f"\r{GREEN}[{label}] Completado en {elapsed}s.{' ' * 20}{RESET}\n")
            return output, exit_code
        if idx == 2:
            child.close(force=True)
            print_ascii_fail(f"La sesion local se cerro inesperadamente ejecutando '{cmd}'.")
            raise RuntimeError(f"EOF inesperado ejecutando '{cmd}'.")
        elapsed += poll_interval
        sys.stdout.write(f"\r{GREEN}[{label}] Tiempo transcurrido: {elapsed}s (max {max_wait_seconds}s)...{RESET}")
        sys.stdout.flush()
        if elapsed >= max_wait_seconds:
            child.close(force=True)
            print_ascii_fail(f"Timeout esperando que finalice '{cmd}'.")
            raise RuntimeError(f"Timeout ({max_wait_seconds}s) esperando la finalizacion de '{cmd}'.")

def _tross_do_login(child):
    print("[*] Ingresando credenciales de login (root / google)...")
    _paced_sendline(child, "root")
    idx = child.expect([r"[Pp]assword:", pexpect.TIMEOUT, pexpect.EOF], timeout=20)
    if idx != 0:
        print_ascii_fail()
        raise RuntimeError("No se recibio el prompt 'Password:' del Tross tras el usuario 'root'.")
    _paced_sendline(child, "google")
    idx = child.expect([TROSS_PROMPT, pexpect.TIMEOUT, pexpect.EOF], timeout=20)
    if idx != 0:
        print_ascii_fail()
        raise RuntimeError("No se pudo iniciar sesion en el Tross (root/google).")

def _tross_netboot_and_login(child):
    _paced_sendline(
        child, "setenv ipaddr 10.0.0.251;setenv netmask 255.255.0.0;setenv gatewayip 10.0.0.254"
    )
    child.expect([UBOOT_PROMPT, pexpect.TIMEOUT], timeout=20)
    _paced_sendline(child, "setenv serverip 10.0.0.254")
    child.expect([UBOOT_PROMPT, pexpect.TIMEOUT], timeout=20)
    _paced_sendline(child, "setenv goog_boot netboot;setenv verify-sig 0;run set_ramboot")
    child.expect([UBOOT_PROMPT, pexpect.TIMEOUT], timeout=20)
    print("[CMD U-Boot] tftpboot 0x70000000 tross/combined.uImage;run boot_kernel")
    _paced_sendline(child, "tftpboot 0x70000000 tross/combined.uImage;run boot_kernel")

    if not _wait_for_pattern_with_enters(child, r"login:", max_seconds=180, interval=5,
                                          label="Esperando prompt 'login:' del Tross"):
        print_ascii_fail("No se recibio el prompt 'login:' del Tross tras el boot por red.")
        raise RuntimeError("Timeout esperando el prompt 'login:' del Tross.")

    _tross_do_login(child)

def _tross_ensure_logged_in(child):
    idx = child.expect([
        TROSS_PROMPT, r"login:", UBOOT_PROMPT, r"Hit any key to stop autoboot",
        pexpect.TIMEOUT, pexpect.EOF
    ], timeout=5)
    if idx == 3:
        print("[!] Se detecto la ventana 'Hit any key to stop autoboot' al reconectar. "
              "Esperando en silencio a que el autoboot termine solo...")
        if not _wait_silently_for_pattern(child, r"login:", max_seconds=210, poll_interval=5,
                                           label="Esperando 'login:' (autoboot en curso al reconectar)"):
            print_ascii_fail("No se recibio el prompt 'login:' tras esperar el autoboot al reconectar.")
            raise RuntimeError("Timeout esperando 'login:' tras reconectar en plena ventana de autoboot.")
        _tross_do_login(child)
        return
    if idx == 0:
        print("[=] La sesion del Tross ya estaba logueada.")
        return
    if idx == 1:
        print("[*] La sesion del Tross esta en el prompt 'login:'. Ingresando credenciales...")
        _tross_do_login(child)
        return
    if idx == 2:
        print("[*] La sesion del Tross esta en el prompt '=>' de U-Boot. Booteando Linux por red...")
        _tross_netboot_and_login(child)
        return

    _paced_sendline(child, "")
    idx = child.expect([TROSS_PROMPT, r"login:", UBOOT_PROMPT, pexpect.TIMEOUT, pexpect.EOF], timeout=30)
    if idx == 0:
        print("[=] La sesion del Tross ya estaba logueada.")
        return
    if idx == 1:
        print("[*] La sesion del Tross esta en el prompt 'login:'. Ingresando credenciales...")
        _tross_do_login(child)
        return
    if idx == 2:
        print("[*] La sesion del Tross esta en el prompt '=>' de U-Boot. Booteando Linux por red...")
        _tross_netboot_and_login(child)
        return

    saw_readonly = ZPE_READONLY_MARKER in (child.before or "")
    if saw_readonly:
        print("[!] Se detecto el aviso de sesion solo-lectura. Reintentando toma de control (Ctrl-X, t)...")
        _zpe_console_take_control(child)
        _drain_buffered_output(child)
        _paced_sendline(child, "")
        idx = child.expect([TROSS_PROMPT, r"login:", UBOOT_PROMPT, pexpect.TIMEOUT, pexpect.EOF], timeout=30)
        if idx == 0:
            print("[=] La sesion del Tross ya estaba logueada.")
            return
        if idx == 1:
            print("[*] La sesion del Tross esta en el prompt 'login:'. Ingresando credenciales...")
            _tross_do_login(child)
            return
        if idx == 2:
            print("[*] La sesion del Tross esta en el prompt '=>' de U-Boot. Booteando Linux por red...")
            _tross_netboot_and_login(child)
            return
        if ZPE_READONLY_MARKER in (child.before or ""):
            print_ascii_fail(
                "La consola del ZPE sigue en modo solo-lectura tras reintentar la toma de control."
            )
            raise _ZpeConsoleReadOnlyError(
                "La consola relay del ZPE esta en modo solo-lectura (aviso "
                f"'{ZPE_READONLY_MARKER}' detectado) tras reconectar."
            )

    print_ascii_fail("No se pudo determinar el estado actual de la sesion del Tross al reconectar.")
    raise RuntimeError("Estado desconocido de la sesion del Tross al reconectar.")

def _tross_reconfigure_zpe_eth1():
    print("[*] Conectando por SSH a admin@10.0.0.253 para reconfigurar ETH1...")
    ssh_cmd = "ssh admin@10.0.0.253"
    print(f"[CMD Interactive] {ssh_cmd}")
    child = pexpect.spawn("bash", ["-c", ssh_cmd], encoding="utf-8", timeout=60)
    child.logfile_read = sys.stdout

    idx = child.expect([
        r"Are you sure you want to continue connecting",
        r"[Pp]assword:",
        pexpect.TIMEOUT,
        pexpect.EOF
    ], timeout=45)

    if idx == 0:
        child.sendline("yes")
        idx = child.expect([r"[Pp]assword:", pexpect.TIMEOUT, pexpect.EOF], timeout=45)
        if idx != 0:
            print_ascii_fail()
            raise RuntimeError("No se recibio el prompt de password SSH del ZPE tras aceptar el fingerprint.")
    elif idx != 1:
        print_ascii_fail()
        raise RuntimeError("No se recibio el prompt de password SSH del ZPE (10.0.0.253).")

    print("[*] Enviando password 'admin'...")
    child.sendline("admin")
    idx = child.expect([r"#\s", pexpect.TIMEOUT, pexpect.EOF], timeout=45)
    if idx != 0:
        print_ascii_fail()
        raise RuntimeError("No se pudo autenticar por SSH contra el ZPE (10.0.0.253).")

    commands = [
        "cd /settings/network_connections/ETH1",
        "set ipv4_mode=static",
        "set ipv4_address=10.0.0.253",
        "set ipv4_bitmask=8",
        "set ipv4_gateway=10.0.0.254",
    ]
    for cmd in commands:
        child.sendline(cmd)
        idx = child.expect([r"#\s", pexpect.TIMEOUT, pexpect.EOF], timeout=30)
        if idx != 0:
            print_ascii_fail()
            child.close(force=True)
            raise RuntimeError(f"El ZPE no respondio como se esperaba tras el comando '{cmd}'.")

    child.sendline("show")
    idx = child.expect([r"#\s", pexpect.TIMEOUT, pexpect.EOF], timeout=30)
    if idx != 0:
        print_ascii_fail()
        child.close(force=True)
        raise RuntimeError("No se recibio la salida del comando 'show' tras configurar ETH1.")

    show_output = child.before or ""
    required_lines = [
        "name: ETH1",
        "type: ethernet",
        "ethernet_interface = eth1",
        "ipv4_mode = static",
        "ipv4_address = 10.0.0.253",
        "ipv4_bitmask = 8",
        "ipv4_gateway = 10.0.0.254",
    ]
    if not all(line in show_output for line in required_lines):
        print_ascii_fail(
            "La salida de 'show' en ETH1 no coincide con lo esperado tras la "
            "reconfiguracion. Se requiere revisión manual (atencion del operador)."
        )
        child.close(force=True)
        raise RuntimeError("Validacion de 'show' en ETH1 fallo tras la reconfiguracion del ZPE.")

    print("[✓] Configuracion de ETH1 validada correctamente.")

    child.sendline("commit")
    child.expect([r"#\s", pexpect.TIMEOUT, pexpect.EOF], timeout=45)

    child.sendline("exit")
    idx = child.expect([
        r"Uncommited changes will be lost\. Confirm exit\? \(yes, no\)",
        r"#\s",
        pexpect.TIMEOUT,
        pexpect.EOF
    ], timeout=20)
    if idx == 0:
        child.sendline("yes")
        child.expect([pexpect.EOF, pexpect.TIMEOUT], timeout=20)

    child.close(force=True)
    print("[✓] Sesion SSH hacia el ZPE cerrada.")

def TROSS_CONFIG():
    if is_tross_step_completed("TROSS_CONFIG"):
        print("[=] Paso 'TROSS_CONFIG' ya fue ejecutado previamente. Omitiendo...")
        return

    while True:
        try:
            _tross_config_attempt()
            return
        except _ZpeConsoleReadOnlyError as e:
            print(f"[!] {e}")
            _print_red_banner(
                "La consola del ZPE quedo atascada en modo solo-lectura y no se pudo "
                "recuperar automaticamente.\n"
                "\n"
                "Por favor reinicie (apague y encienda) el propio ZPE y presione ENTER "
                "en cuanto haya vuelto a encender."
            )
            input("Presione ENTER despues de reiniciar el ZPE...")
            _green_wait(60, "Esperando a que el ZPE termine de levantar")
            print("[*] Reintentando TROSS_CONFIG (retomando en la ultima etapa pendiente)...")

def _tross_stage_dhcp(tross_mac):
    if is_tross_step_completed("tross_dhcp_applied"):
        print("[=] Etapa 'tross_dhcp_applied' ya fue ejecutada previamente. Omitiendo...")
        return
    print("--- ETAPA 1/13: Aplicar la MAC del Tross en /etc/dhcp/dhcpd.conf ---")

    print(f"[*] Asegurando que /etc/dhcp/dhcpd.conf tenga la MAC del Tross ({tross_mac})...")
    new_line = f"host tross {{ hardware ethernet {tross_mac}; fixed-address 10.0.0.251; }}"
    sed_cmd = (
        "sudo sed -i '/host tross { hardware ethernet/c\\"
        f"{new_line}' /etc/dhcp/dhcpd.conf"
    )
    run_interactive(sed_cmd)
    run_interactive(f"sudo grep -q '{tross_mac}' /etc/dhcp/dhcpd.conf")

    print("[*] Reiniciando servicios DHCP (IPv4 e IPv6)...")
    run_interactive("sudo systemctl restart isc-dhcp-server")
    run_interactive("sudo systemctl restart isc-dhcp-server6")

    mark_tross_step_completed("tross_dhcp_applied")

def _tross_stage_flash_uboot():
    if is_tross_step_completed("tross_uboot_flashed"):
        print("[=] Etapa 'tross_uboot_flashed' ya fue ejecutada previamente. Omitiendo...")
        return
    print("--- ETAPA 2/13: Interrumpir el arranque y flashear U-Boot del Tross ---")

    _print_yellow_banner(
        "Conecte un cable consola (TROSS) al puerto CONSOLE del TROSS y el "
        "otro extremo al puerto 17 del ZPE."
    )
    input("Presione ENTER para continuar...")

    child = _open_zpe_console_telnet(7017, take_control=True)
    try:
        _print_yellow_banner(
            "Ya se establecio la conexion a la consola del Tross. Ahora reinicie "
            "FISICAMENTE el Tross de forma manual (apague y encienda, o presione "
            "el boton de reset) y presione ENTER en cuanto lo haya hecho."
        )
        input("Presione ENTER despues de reiniciar manualmente el Tross...")

        _uboot_break_spam(child)

        while True:
            _paced_sendline(
                child, "setenv ipaddr 10.0.0.251;setenv netmask 255.255.0.0;setenv gatewayip 10.0.0.254"
            )
            child.expect([UBOOT_PROMPT, pexpect.TIMEOUT], timeout=20)
            _paced_sendline(child, "setenv serverip 10.0.0.254")
            child.expect([UBOOT_PROMPT, pexpect.TIMEOUT], timeout=20)

            print("[CMD U-Boot] tftpboot 0x60000000 tross/uboot_planet-hurricane3.bin")
            _paced_sendline(child, "tftpboot 0x60000000 tross/uboot_planet-hurricane3.bin")
            idx = child.expect([r"Load address: 0x60000000", pexpect.TIMEOUT, pexpect.EOF], timeout=90)
            output = child.before or ""
            required = [
                "Change GMAC speed to 1000MB",
                "Using gmac-0@mdk device",
                "TFTP from server 10.0.0.254",
                "our IP address is 10.0.0.251",
                "Filename 'tross/uboot_planet-hurricane3.bin'",
            ]
            if idx == 0 and all(m in output for m in required):
                print("[✓] Respuesta de 'tftpboot' (paso1) validada correctamente.")
                child.expect([UBOOT_PROMPT, pexpect.TIMEOUT], timeout=20)
                break
            print("[!] La respuesta de 'tftpboot' no cumplio lo esperado (paso1). Reintentando paso1...")

        _uboot_cmd_check(
            child, "sf probe",
            "SF: Detected MX25L12805 with page size 256 Bytes, erase size 64 KiB, total 16 MiB"
        )
        _uboot_cmd_check(
            child, "sf erase 0x0 0x100000",
            "SF: 1048576 bytes @ 0x0 Erased: OK"
        )
        _uboot_cmd_check(
            child, "sf write 0x60000000 0x0 0x100000",
            "SF: 1048576 bytes @ 0x0 Written: OK"
        )
        _uboot_cmd_check(
            child, "sf erase 0x1c0000 0x10000",
            "SF: 65536 bytes @ 0x1c0000 Erased: OK"
        )

        print("[CMD U-Boot] reset")
        _paced_sendline(child, "reset")
        _uboot_break_spam(child)
        print("[✓] U-Boot flasheado; el Tross quedo esperando en el prompt '=>'.")
    finally:
        _zpe_console_exit(child)

    mark_tross_step_completed("tross_uboot_flashed")

def _tross_stage_boot_linux():
    if is_tross_step_completed("tross_linux_booted"):
        print("[=] Etapa 'tross_linux_booted' ya fue ejecutada previamente. Omitiendo...")
        return
    print("--- ETAPA 3/13: Bootear Linux por red y validar el kernel ---")

    child = _open_zpe_console_telnet(7017)
    try:
        _tross_ensure_logged_in(child)

        _paced_sendline(child, "killall rcS")
        child.expect([TROSS_PROMPT, pexpect.TIMEOUT, pexpect.EOF], timeout=30)

        _run_tross_cmd_and_wait(
            child, "uname -a", max_wait_seconds=30, poll_interval=5,
            label="Validando kernel del Tross"
        )
        uname_output = child.before or ""
        if "4.19.238-planet-hurricane3 #1" not in uname_output:
            print_ascii_fail("La version de kernel del Tross no coincide con la esperada (uname -a).")
            raise RuntimeError("Validacion de 'uname -a' fallo en el Tross.")
        print("[✓] Kernel del Tross validado (4.19.238-planet-hurricane3 #1).")
    finally:
        _zpe_console_exit(child)

    mark_tross_step_completed("tross_linux_booted")

def _tross_stage_download_imageset():
    if is_tross_step_completed("tross_imageset_downloaded"):
        print("[=] Etapa 'tross_imageset_downloaded' ya fue ejecutada previamente. Omitiendo...")
        return
    print("--- ETAPA 4/13: Descargar y validar imageset.tgz por TFTP ---")

    child = _open_zpe_console_telnet(7017)
    try:
        _tross_ensure_logged_in(child)

        _paced_sendline(child, "cd /tmp")
        child.expect([TROSS_PROMPT, pexpect.TIMEOUT, pexpect.EOF], timeout=20)

        MAC_MISMATCH_MARKERS = ("server write failed", "Network is unreachable")
        TRANSIENT_FAILURE_MARKERS = ("Retry limit exceeded", "server read timed out")

        while True:
            tftp_output = _run_tross_cmd_and_wait(
                child, "tftp -g -r tross/imageset.tgz 10.0.0.254",
                max_wait_seconds=240, poll_interval=5,
                label="Descargando imageset.tgz por tftp"
            )
            is_mac_mismatch = any(m in tftp_output for m in MAC_MISMATCH_MARKERS)
            is_transient_failure = any(m in tftp_output for m in TRANSIENT_FAILURE_MARKERS)
            if is_mac_mismatch:
                _print_red_banner(
                    "La MAC del Tross no coincide. Corrijala en otra terminal con:\n"
                    "\n"
                    "sudo gedit /etc/dhcp/dhcpd.conf\n"
                    "\n"
                    "y reinicie los servicios con:\n"
                    "\n"
                    "sudo systemctl restart isc-dhcp-server\n"
                    "sudo systemctl restart isc-dhcp-server6\n"
                    "\n"
                    "Presione ENTER para continuar."
                )
                input("Presione ENTER para continuar...")
                continue
            if is_transient_failure:
                _print_red_banner(
                    "La descarga de imageset.tgz por TFTP fallo por timeout "
                    "('Retry limit exceeded' / 'server read timed out'), no por "
                    "mismatch de MAC. Puede deberse a un corte momentaneo de red.\n"
                    "\n"
                    "Verifique la conectividad de red hacia 10.0.0.254 si el problema "
                    "persiste tras varios reintentos.\n"
                    "\n"
                    "Presione ENTER para reintentar la descarga."
                )
                input("Presione ENTER para continuar...")
                continue
            print("[✓] Descarga de imageset.tgz completada sin errores de red.")
            break

        if not _wait_for_pattern_with_enters(child, r"root@:/tmp", max_seconds=240, interval=5,
                                              label="Esperando prompt 'root@:/tmp'"):
            print_ascii_fail("No se recibio el prompt 'root@:/tmp' tras esperar 4 minutos.")
            raise RuntimeError("Timeout esperando el prompt 'root@:/tmp' del Tross.")

        ls_output = _run_tross_cmd_and_wait(child, "ls", max_wait_seconds=30, poll_interval=5,
                                             label="Listando /tmp")
        expected_files = ["StatsWB.Flow.lock", "StatsWB.Port.lock", "core", "imageset.tgz", "sandcastle"]
        if not all(f in ls_output for f in expected_files):
            print_ascii_fail("El listado de /tmp en el Tross no contiene los archivos esperados.")
            raise RuntimeError("Validacion de 'ls' fallo en el Tross.")
        print("[✓] Listado de /tmp validado correctamente.")

        md5_output = _run_tross_cmd_and_wait(
            child, "md5sum imageset.tgz", max_wait_seconds=45, poll_interval=5,
            label="Calculando md5sum de imageset.tgz"
        )
        if "3e52decb2b76aa84f83c5ae97e520c77" not in md5_output:
            print_ascii_fail("El md5sum de imageset.tgz no coincide con el esperado.")
            raise RuntimeError("Validacion de 'md5sum' fallo en el Tross.")
        print("[✓] md5sum de imageset.tgz validado correctamente.")
    finally:
        _zpe_console_exit(child)

    mark_tross_step_completed("tross_imageset_downloaded")

def _tross_stage_run_imager():
    if is_tross_step_completed("tross_imager_done"):
        print("[=] Etapa 'tross_imager_done' ya fue ejecutada previamente. Omitiendo...")
        return
    print("--- ETAPA 5/13: Extraer e imagear el Tross (tar + imager, ~20 minutos) ---")

    child = _open_zpe_console_telnet(7017)
    try:
        _tross_ensure_logged_in(child)
        _paced_sendline(child, "cd /tmp")
        child.expect([TROSS_PROMPT, pexpect.TIMEOUT, pexpect.EOF], timeout=20)

        imager_output = _run_tross_cmd_and_wait(
            child,
            "tar Oxzf imageset.tgz tools-cf.tgz | tar xz && netconfig=no ./imager ab",
            max_wait_seconds=1800, poll_interval=10,
            label="Ejecutando imager (aprox. 20 minutos)"
        )
        required_tail = [
            "md5 of '/tmp/imageset.tgz' = 142c29970d23c3e4819f144812a64b79",
            "sudo mount -a -t vfat",
            "Setting regionselect to a/0",
            "sync",
        ]
        if not all(s in imager_output for s in required_tail):
            print_ascii_fail(
                "La salida del comando 'imager' no contiene lo esperado. "
                "Se requiere atencion del operador."
            )
            raise RuntimeError("Validacion de la salida de 'imager' fallo en el Tross.")
        print("[✓] Imageo del Tross completado y validado correctamente.")
    finally:
        _zpe_console_exit(child)

    mark_tross_step_completed("tross_imager_done")

def _tross_stage_bootenv():
    if is_tross_step_completed("tross_bootenv_saved"):
        print("[=] Etapa 'tross_bootenv_saved' ya fue ejecutada previamente. Omitiendo...")
        return
    print("--- ETAPA 6/13: Guardar bootcase_1/bootdelay y volver a loguear ---")

    child = _open_zpe_console_telnet(7017)
    try:
        _tross_ensure_logged_in(child)

        print("[CMD Tross] reboot")
        _paced_sendline(child, "reboot")
        _uboot_break_spam(child)

        _paced_sendline(child, 'setenv bootcase_1 "bootcount 2;run pri_cf_bootcmd"')
        child.expect([UBOOT_PROMPT, pexpect.TIMEOUT], timeout=20)
        _paced_sendline(child, "setenv bootdelay 3")
        child.expect([UBOOT_PROMPT, pexpect.TIMEOUT], timeout=20)

        _uboot_cmd_check(
            child, "saveenv",
            ["Saving Environment to SPI Flash...",
             "SF: Detected MX25L12805 with page size 256 Bytes, erase size 64 KiB, total 16 MiB",
             "Erasing SPI flash...Writing to SPI flash...done"],
            timeout=45,
            fail_msg="La respuesta de 'saveenv' no es la esperada. Se requiere atencion del operador."
        )

        print("[CMD U-Boot] reset")
        _paced_sendline(child, "reset")
        if not _wait_silently_for_pattern(child, r"login:", max_seconds=210, poll_interval=5,
                                           label="Esperando prompt 'login:' tras reset (sin enviar teclas)"):
            print_ascii_fail("No se recibio el prompt 'login:' del Tross tras 'reset'.")
            raise RuntimeError("Timeout esperando el prompt 'login:' del Tross tras 'reset'.")

        _tross_do_login(child)
    finally:
        _zpe_console_exit(child)

    mark_tross_step_completed("tross_bootenv_saved")

def _tross_stage_zpe_eth1():
    if is_tross_step_completed("tross_zpe_eth1_reconfigured"):
        print("[=] Etapa 'tross_zpe_eth1_reconfigured' ya fue ejecutada previamente. Omitiendo...")
        return
    print("--- ETAPA 7/13: Reconfigurar ETH1 del ZPE via SSH (10.0.0.253 estatica) ---")

    _tross_reconfigure_zpe_eth1()

    mark_tross_step_completed("tross_zpe_eth1_reconfigured")

def _tross_stage_lease(tross_mac):
    if is_tross_step_completed("tross_lease_detected"):
        print("[=] Etapa 'tross_lease_detected' ya fue ejecutada previamente. Omitiendo...")
        return
    print("--- ETAPA 8/13: Detectar el 'lease' de red del Tross y validarlo con ping ---")

    child = _open_zpe_console_telnet(7017)
    try:
        _tross_ensure_logged_in(child)

        target_mac = _mac_plus_offset(tross_mac, 2)
        print(f"[*] Buscando el lease asociado a la MAC {target_mac} (tross_mac + 2)...")

        LEASE_WAIT_MAX_SECONDS = 180
        LEASE_WAIT_POLL_SECONDS = 15
        matches = []
        elapsed = 0
        while True:
            leases_output = _run_tross_cmd_and_wait(
                child, "cat /mnt/region_config/dhcpd/dhcpd.rymden.leases",
                max_wait_seconds=45, poll_interval=5, label="Leyendo leases del ZPE"
            )
            blocks = re.findall(r"lease\s+([\d.]+)\s*\{(.*?)\n\}", leases_output, re.DOTALL)
            matches = [ip for ip, body in blocks if target_mac.lower() in body.lower()]
            if matches:
                break
            if elapsed >= LEASE_WAIT_MAX_SECONDS:
                break
            print(f"[=] Todavia no aparece un lease para {target_mac}; puede que el Tross aun no haya "
                  f"renovado su DHCP contra la red recien reconfigurada. Reintentando en "
                  f"{LEASE_WAIT_POLL_SECONDS}s (maximo {LEASE_WAIT_MAX_SECONDS}s)...")
            _green_wait(LEASE_WAIT_POLL_SECONDS, "Esperando a que aparezca el lease del Tross")
            elapsed += LEASE_WAIT_POLL_SECONDS

        if not matches:
            print_ascii_fail(f"No se encontro ningun lease asociado a la MAC {target_mac} en el ZPE.")
            raise RuntimeError("No se pudo determinar 'tross_lease' a partir de las leases del ZPE.")

        tross_lease = matches[-1]
        print(f"[+] tross_lease detectado: {tross_lease}")

        print(f"[*] Pingueando {tross_lease} desde la consola del ZPE...")
        _paced_sendline(child, f"ping -c 3 {tross_lease}")
        idx = child.expect([r"64 bytes from", pexpect.TIMEOUT, pexpect.EOF], timeout=45)
        if idx != 0:
            print_ascii_fail(f"No se recibio respuesta de ping desde {tross_lease}.")
            raise RuntimeError("Validacion de 'ping' al tross_lease fallo.")
        child.expect([TROSS_PROMPT, pexpect.TIMEOUT, pexpect.EOF], timeout=20)
        print(f"[✓] Ping a {tross_lease} exitoso.")
    finally:
        _zpe_console_exit(child)

    mark_tross_step_completed("tross_lease_detected", {"tross_lease": tross_lease})

def _tross_stage_vrmu_flash(tross_lease):
    if is_tross_step_completed("tross_vrmu_flash_done"):
        print("[=] Etapa 'tross_vrmu_flash_done' ya fue ejecutada previamente. Omitiendo...")
        return
    print("--- ETAPA 9/13: Flasheo del Tross via vrmu_util (2 corridas, ~10 min c/u) ---")

    sudo_user = os.environ.get('SUDO_USER', 'testusr')
    home_dir = f"/home/{sudo_user}"
    flash_cmd = (
        f"cd {home_dir} && ./vrmu_util --api=/rmu_util --api=/macros/flash "
        f"--hostname={tross_lease} --srec_prefix=ledare_1_8_5 --logtostderr "
        f"--envelope_enabled=false"
    )

    print("[*] Ejecutando vrmu_util (flash) - intento 1/2...")
    _run_local_cmd_with_wait(
        flash_cmd, max_wait_seconds=900, poll_interval=10,
        label="vrmu_util flash (intento 1/2)"
    )

    _green_wait(600, "Esperando los 10 minutos obligatorios antes de repetir el flash")

    print("[*] Ejecutando vrmu_util (flash) - intento 2/2...")
    _run_local_cmd_with_wait(
        flash_cmd, max_wait_seconds=900, poll_interval=10,
        label="vrmu_util flash (intento 2/2)"
    )

    mark_tross_step_completed("tross_vrmu_flash_done")

def _tross_stage_vrmu_upgrade(tross_lease):
    if is_tross_step_completed("tross_vrmu_upgrade_done"):
        print("[=] Etapa 'tross_vrmu_upgrade_done' ya fue ejecutada previamente. Omitiendo...")
        return
    print("--- ETAPA 10/13: Actualizacion de firmware periferico via vrmu_util ---")

    sudo_user = os.environ.get('SUDO_USER', 'testusr')
    home_dir = f"/home/{sudo_user}"
    upgrade_cmd = (
        f"cd {home_dir} && ./vrmu_util --envelope_enabled=false --hostname={tross_lease} "
        f"--logtostderr --api=/api/peripheral/upgrade "
        f"--peripheral_firmware_filename=FWContainer_EN_3_AP_00_02_00_09.bin"
    )
    print("[*] Ejecutando vrmu_util (peripheral upgrade)...")
    upgrade_output, _ = _run_local_cmd_with_wait(
        upgrade_cmd, max_wait_seconds=900, poll_interval=10,
        label="vrmu_util peripheral upgrade"
    )

    if "INTERNAL: Upgrade failed: 1" in upgrade_output:
        print_ascii_fail("La actualizacion de firmware periferico del Tross fallo (Upgrade failed: 1).")
        raise RuntimeError("vrmu_util peripheral upgrade reporto 'Upgrade failed: 1'.")
    elif "INTERNAL: Upgrade failed: 2" in upgrade_output:
        print("[✓] vrmu_util peripheral upgrade completado (respuesta esperada: 'Upgrade failed: 2').")
    else:
        print_ascii_fail(
            "La respuesta de vrmu_util (peripheral upgrade) no coincide con ninguno de los "
            "resultados esperados. Se requiere atencion del operador."
        )
        raise RuntimeError("Respuesta inesperada de vrmu_util en 'peripheral upgrade'.")

    mark_tross_step_completed("tross_vrmu_upgrade_done")

TROSS_LEDARE_FW_VERSION = "1.8.5"

def _tross_stage_vrmu_fw_version_check(tross_lease):
    if is_tross_step_completed("tross_vrmu_fw_version_checked"):
        print("[=] Etapa 'tross_vrmu_fw_version_checked' ya fue ejecutada previamente. Omitiendo...")
        return
    print("--- ETAPA 11/13: Verificar version de firmware (fw-version) ---")

    sudo_user = os.environ.get('SUDO_USER', 'testusr')
    home_dir = f"/home/{sudo_user}"
    fw_version_cmd = (
        f"cd {home_dir} && ./vrmu_util --hostname={tross_lease} --envelope_enabled=false "
        f"| grep -a4 fw-version"
    )
    expected_version_string = f"Ledare {TROSS_LEDARE_FW_VERSION}"
    flash_block_pattern = re.compile(
        r'streamz_name:\s*"/flash/fw-version".*?string_value:\s*"([^"]*)"', re.DOTALL
    )

    FW_VERSION_MAX_WAIT_SECONDS = 300
    FW_VERSION_POLL_SECONDS = 30
    elapsed = 0
    fw_output = ""
    current_version = None
    while True:
        print("[*] Ejecutando vrmu_util para verificar fw-version...")
        fw_output, _ = _run_local_cmd_with_wait(
            fw_version_cmd, max_wait_seconds=120, poll_interval=5,
            label="Verificando fw-version"
        )

        match = flash_block_pattern.search(fw_output)
        current_version = match.group(1) if match else None

        if current_version == expected_version_string:
            print(f'[✓] Version de firmware del Ledare validada correctamente '
                  f'(string_value: "{expected_version_string}").')
            mark_tross_step_completed("tross_vrmu_fw_version_checked")
            return

        if elapsed >= FW_VERSION_MAX_WAIT_SECONDS:
            break

        if current_version:
            print(f"[=] La version de firmware del Ledare todavia es \"{current_version}\" "
                  f"(se espera \"{expected_version_string}\"); el Tross puede seguir aplicando "
                  f"el cambio en segundo plano. Reintentando en {FW_VERSION_POLL_SECONDS}s "
                  f"(maximo {FW_VERSION_MAX_WAIT_SECONDS}s)...")
        else:
            print(f"[!] No se encontro el bloque 'streamz_name: \"/flash/fw-version\"' en la "
                  f"salida. Reintentando en {FW_VERSION_POLL_SECONDS}s "
                  f"(maximo {FW_VERSION_MAX_WAIT_SECONDS}s)...")
        _green_wait(FW_VERSION_POLL_SECONDS, "Esperando a que el Tross termine de aplicar el firmware")
        elapsed += FW_VERSION_POLL_SECONDS

    if current_version:
        print_ascii_fail(
            f'La version de firmware del Ledare quedo en "{current_version}" (se esperaba '
            f'"{expected_version_string}") tras esperar varios minutos despues del upgrade. '
            f"Se requiere atencion del operador."
        )
        raise RuntimeError(
            f'Validacion de fw-version fallo: version actual "{current_version}", '
            f'esperada "{expected_version_string}".'
        )
    else:
        print_ascii_fail(
            "No se pudo encontrar el bloque 'streamz_name: \"/flash/fw-version\"' en la "
            "salida de vrmu_util tras varios intentos."
        )
        raise RuntimeError("No se pudo determinar la version de firmware del Ledare (fw-version).")

def _parse_rectifier_voltages(dc_voltage_output):
    pattern = re.compile(
        r'streamz_name:\s*"/rectifier/dc-voltage".*?device_name:\s*"([^"]*)".*?'
        r'units:\s*"volts".*?float_value:\s*([\-0-9.]+)',
        re.DOTALL
    )
    return [(m.group(1), float(m.group(2))) for m in pattern.finditer(dc_voltage_output)]

def _ping_until_up(ip, description, max_wait_seconds=300, poll_interval=10):
    print(f"[*] Esperando a que {description} ({ip}) responda ping...")
    elapsed = 0
    while True:
        result = subprocess.run(
            f"ping -c 1 -W 2 {ip}", shell=True,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        if result.returncode == 0:
            print(f"[✓] {description} ({ip}) respondio ping.")
            return True
        if elapsed >= max_wait_seconds:
            return False
        _green_wait(poll_interval, f"Esperando ping de {description} ({ip})")
        elapsed += poll_interval

def _tross_validate_instruments_after_power_cycle():
    print("--- Validando instrumentos tras el power-cycle del rack (Juniper -> ZPE -> Tross) ---")

    if not _ping_until_up("10.0.0.254", "Juniper", max_wait_seconds=300, poll_interval=10):
        print_ascii_fail("El Juniper (10.0.0.254) no respondio ping tras el power-cycle del rack.")
        raise RuntimeError("Validacion de instrumentos fallo: Juniper (10.0.0.254) sin ping.")

    if not _ping_until_up("10.0.0.253", "ZPE", max_wait_seconds=300, poll_interval=10):
        print_ascii_fail("El ZPE (10.0.0.253) no respondio ping tras el power-cycle del rack.")
        raise RuntimeError("Validacion de instrumentos fallo: ZPE (10.0.0.253) sin ping.")

    print("[*] Validando que el Tross haya terminado de bootear (via telnet a traves del ZPE)...")
    child = _open_zpe_console_telnet(7017)
    try:
        _tross_ensure_logged_in(child)
        print("[✓] El Tross boot\u00f3 correctamente y esta accesible via consola.")
    finally:
        _zpe_console_exit(child)

    _green_wait(600, "Esperando 10 minutos tras validar el booteo del Tross (estabilizacion)")

    print("[✓] Validacion de instrumentos completa: Juniper, ZPE y Tross arriba.")

def _measure_rectifier_voltages_with_retry(tross_lease, max_retries=3, retry_wait_seconds=300):
    sudo_user = os.environ.get('SUDO_USER', 'testusr')
    home_dir = f"/home/{sudo_user}"
    dc_voltage_cmd = (
        f"cd {home_dir} && ./vrmu_util --hostname={tross_lease} --envelope_enabled=false "
        f"| grep -a4 dc-voltage"
    )

    for intento in range(1, max_retries + 1):
        print(f"[*] Ejecutando vrmu_util para medir el voltaje DC de los rectificadores "
              f"(intento {intento}/{max_retries})...")
        dc_output, _ = _run_local_cmd_with_wait(
            dc_voltage_cmd, max_wait_seconds=60, poll_interval=5,
            label="Verificando dc-voltage"
        )
        readings = _parse_rectifier_voltages(dc_output)
        all_zero = bool(readings) and all(voltage == 0 for _, voltage in readings)

        if readings and not all_zero:
            return readings

        if not readings:
            print(f"[!] No se encontro ninguna lectura de dc-voltage (intento {intento}/{max_retries}). "
                  f"Puede que el servicio de telemetria del Tross todavia este levantando.")
        else:
            print(f"[!] Todas las lecturas de dc-voltage dieron 0 (intento {intento}/{max_retries}).")

        if intento < max_retries:
            _green_wait(retry_wait_seconds,
                        f"Esperando antes del reintento {intento + 1}/{max_retries}")

    _print_red_banner(
        f"No se pudieron obtener lecturas validas de dc-voltage tras {max_retries} intentos "
        f"(con {retry_wait_seconds // 60} minutos de espera entre cada uno).\n"
        "\n"
        "Se recomienda reiniciar la configuracion completa del Tross desde cero."
    )
    respuesta = input(
        "¿Desea borrar el estado del Tross (tross_config.json) y empezar de nuevo? (y/n): "
    ).strip().lower()

    if respuesta == "y":
        print(f"[*] Borrando {TROSS_STATE_FILE} (y su respaldo) para empezar de cero...")
        for path in (TROSS_STATE_FILE, TROSS_STATE_FILE + ".bak"):
            try:
                if os.path.exists(path):
                    os.remove(path)
            except Exception as e:
                print(f"[!] Advertencia: no se pudo borrar '{path}' automaticamente ({e}). "
                      f"Borralo manualmente antes de reintentar.")
        raise RuntimeError(
            "No se obtuvieron lecturas validas de dc-voltage tras varios reintentos. Se borro "
            "el estado del Tross (tross_config.json); hay que iniciar la configuracion del "
            "Tross de nuevo desde cero."
        )

    raise RuntimeError(
        "No se obtuvieron lecturas validas de dc-voltage tras varios reintentos. El estado del "
        "Tross se dejo intacto; se puede volver a correr el script para reintentar sin perder "
        "el progreso ya hecho."
    )

def _tross_stage_voltage_check(tross_lease):
    if is_tross_step_completed("tross_voltage_check_done"):
        print("[=] Etapa 'tross_voltage_check_done' ya fue ejecutada previamente. Omitiendo...")
        return
    print("--- ETAPA 12/13: Validar voltaje DC de los rectificadores (dc-voltage) ---")

    awaiting_power_cycle = is_tross_step_completed("tross_voltage_check_awaiting_power_cycle")
    if awaiting_power_cycle:
        _tross_validate_instruments_after_power_cycle()

    readings = _measure_rectifier_voltages_with_retry(tross_lease, max_retries=3, retry_wait_seconds=300)

    print("[*] Lecturas de voltaje DC por rectificador:")
    for device_name, voltage in readings:
        marker = "✓" if voltage > 50 else "✗"
        print(f"    [{marker}] {device_name}: {voltage} V")

    all_ok = all(voltage > 50 for _, voltage in readings)

    if all_ok:
        print("[✓] Todos los rectificadores miden un voltaje DC > 50V.")
        mark_tross_step_completed("tross_voltage_check_done")
        return

    if not awaiting_power_cycle:
        mark_tross_step_completed("tross_voltage_check_awaiting_power_cycle")
        _print_yellow_banner(
            "Se detectaron rectificadores con voltaje DC <= 50V (se esperaba > 50V en TODOS).\n"
            "\n"
            "Por favor realice un POWER CYCLE DEL RACK COMPLETO (apague y encienda todo el "
            "rack, no solo el Tross).\n"
            "\n"
            "Una vez que el rack haya terminado de volver a encender, vuelva a correr "
            "gf_provisioning.py: esta validacion de voltaje se repetira automaticamente."
        )
        print("[*] Terminando el programa de forma segura antes del power-cycle del rack...")
        sys.exit(0)

    print_ascii_fail(
        "El voltaje DC de los rectificadores sigue <= 50V incluso despues del power-cycle "
        "del rack. Se considera que la configuracion del Tross fallo de forma irrecuperable; "
        "hay que rehacerla desde cero."
    )
    print(f"[*] Borrando {TROSS_STATE_FILE} (y su respaldo) para forzar rehacer todo el "
          f"proceso del Tross desde cero en el proximo intento...")
    for path in (TROSS_STATE_FILE, TROSS_STATE_FILE + ".bak"):
        try:
            if os.path.exists(path):
                os.remove(path)
        except Exception as e:
            print(f"[!] Advertencia: no se pudo borrar '{path}' automaticamente ({e}). "
                  f"Borralo manualmente antes de reintentar.")
    raise RuntimeError(
        "Validacion de voltaje DC fallo tras el power-cycle del rack. Se borro el estado del "
        "Tross (tross_config.json); hay que iniciar la configuracion del Tross de nuevo desde cero."
    )

def _tross_stage_voltage_sequence_test(tross_lease):
    if is_tross_step_completed("tross_voltage_sequence_tested"):
        print("[=] Etapa 'tross_voltage_sequence_tested' ya fue ejecutada previamente. Omitiendo...")
        return
    print("--- ETAPA 13/13: Prueba de secuencia de voltaje (45V/15s) en los rectificadores ---")

    sudo_user = os.environ.get('SUDO_USER', 'testusr')
    home_dir = f"/home/{sudo_user}"
    sequence_cmd = (
        f'cd {home_dir} && ./vrmu_util --hostname={tross_lease} --envelope_enabled=false '
        f'--api="/api/rectifier/outputsequence" --rectifier_output_sequence="45:100:15" 2>&1'
    )
    dc_voltage_cmd = (
        f"cd {home_dir} && ./vrmu_util --hostname={tross_lease} --envelope_enabled=false "
        f"| grep -a4 dc-voltage"
    )

    print("[*] Enviando secuencia de voltaje (45V durante 15s) a los rectificadores...")
    _run_local_cmd_with_wait(
        sequence_cmd, max_wait_seconds=60, poll_interval=5,
        label="Ejecutando outputsequence (45V/15s)"
    )

    print("[*] Verificando que el voltaje DC haya caido al rango esperado (>40V y <50V)...")
    dc_output, _ = _run_local_cmd_with_wait(
        dc_voltage_cmd, max_wait_seconds=60, poll_interval=5,
        label="Verificando dc-voltage tras la secuencia"
    )

    readings = _parse_rectifier_voltages(dc_output)
    if not readings:
        print_ascii_fail(
            "No se encontro ninguna lectura de dc-voltage tras la secuencia de prueba."
        )
        raise RuntimeError(
            "No se pudieron obtener lecturas de dc-voltage tras la secuencia de voltaje."
        )

    print("[*] Lecturas de voltaje DC tras la secuencia:")
    for device_name, voltage in readings:
        marker = "✓" if 40 < voltage < 50 else "✗"
        print(f"    [{marker}] {device_name}: {voltage} V")

    all_in_range = all(40 < voltage < 50 for _, voltage in readings)
    if not all_in_range:
        print_ascii_fail(
            "No todos los rectificadores cayeron al rango esperado (>40V y <50V) tras la "
            "secuencia de prueba. Se requiere atencion del operador."
        )
        raise RuntimeError("La prueba de secuencia de voltaje (45V/15s) fallo.")

    print("[✓] Todos los rectificadores respondieron correctamente a la secuencia de voltaje "
          "(quedaron entre 40V y 50V).")
    mark_tross_step_completed("tross_voltage_sequence_tested")

def _tross_config_attempt():
    print("--- PASO: TROSS_CONFIG - Configuracion automatica del Tross ---")

    state = load_state()
    tross_mac = state.get("config", {}).get("tross_mac")
    if not tross_mac:
        raise RuntimeError(
            "No se encontro 'tross_mac' en el estado. Asegurate de correr "
            "'tross_capture_mac' antes de 'TROSS_CONFIG'."
        )

    _tross_stage_dhcp(tross_mac)
    _tross_stage_flash_uboot()
    _tross_stage_boot_linux()
    _tross_stage_download_imageset()
    _tross_stage_run_imager()
    _tross_stage_bootenv()
    _tross_stage_zpe_eth1()
    _tross_stage_lease(tross_mac)

    tross_lease = load_tross_state().get("config", {}).get("tross_lease")
    if not tross_lease:
        raise RuntimeError(
            "No se encontro 'tross_lease' en el estado tras la etapa de deteccion del lease."
        )

    _tross_stage_vrmu_flash(tross_lease)
    _tross_stage_vrmu_upgrade(tross_lease)
    _tross_stage_vrmu_fw_version_check(tross_lease)
    _tross_stage_voltage_check(tross_lease)
    _tross_stage_voltage_sequence_test(tross_lease)

    _print_green_banner("CONFIGURACION DEL TROSS (TROSS_CONFIG) COMPLETADA EXITOSAMENTE.")
    mark_tross_step_completed("TROSS_CONFIG")

def download_python_tools():
    if is_step_completed("download_python_tools"):
        print("[=] Paso 'download_python_tools' ya fue ejecutado previamente. Omitiendo...")
        return

    print("--- PASO: Descarga de Herramientas Python por SCP ---")
    
    remote_host = "172.24.125.174"
    sudo_user = os.environ.get('SUDO_USER', 'testusr')
    remote_user = sudo_user
    
    files_to_download = [
        "dhcpd.py",
        "UUT_test_case.py",
        "share.py",
        "reboot.py",
        "U22Tocinos"
    ]
    
    destination_dir = "."
    
    for filename in files_to_download:
        remote_path = f"{remote_user}@{remote_host}:/home/{remote_user}/{filename}"
        cmd = f"scp {remote_path} {destination_dir}/"

        def _download_once(filename=filename, cmd=cmd):
            print(f"[*] Descargando {filename} por SCP...")
            print(f"[CMD Interactive] {cmd}")

            child = pexpect.spawn("bash", ["-c", cmd], encoding="utf-8", timeout=None)

            class PexpectLogger:
                def write(self, text):
                    sys.stdout.write(text)
                    sys.stdout.flush()
                def flush(self):
                    sys.stdout.flush()

            child.logfile_read = PexpectLogger()

            while True:
                idx = child.expect([
                    r"Are you sure you want to continue connecting",
                    r"password:",
                    pexpect.EOF
                ], timeout=None)

                if idx == 0:
                    print("\n[*] Detectado prompt de huella SSH. Enviando 'yes'...")
                    child.sendline("yes")
                elif idx == 1:
                    print("\n[*] Ingresando contraseña para SCP...")
                    child.sendline(SUDO_PASSWORD)
                elif idx == 2:
                    break

            child.close()

            if child.exitstatus != 0:
                raise RuntimeError(f"Error descargando {filename} por SCP (Exit code: {child.exitstatus})")

        try:
            _retry_download(_download_once, f"descarga de {filename} por SCP")
        except RuntimeError:
            print_ascii_fail(f"No se pudo descargar {filename} por SCP tras varios intentos.")
            raise

    print("[✓] Todas las herramientas fueron descargadas exitosamente.")
    mark_step_completed("download_python_tools")

def fix_chrome():
    if is_step_completed("fix_chrome"):
        print("[=] Paso 'fix_chrome' ya fue ejecutado previamente. Omitiendo...")
        return

    print("--- PASO: Eliminación y Reinstalación Limpia de Google Chrome ---")

    print("[*] Eliminando y purgando Google Chrome...")
    run_interactive("sudo apt-get purge google-chrome-stable -y")
    run_interactive("sudo apt-get autoremove -y")
    run_interactive("sudo apt-get clean -y")

    print("[*] Limpiando archivos de configuración residuales y llaves GPG antiguas...")
    run_command("sudo rm -f /etc/apt/trusted.gpg.d/google-chrome.gpg", check=False)
    run_command("sudo rm -f /etc/apt/sources.list.d/google-chrome.list", check=False)
    run_command("sudo rm -rf ~/.config/google-chrome", check=False)
    run_command("sudo rm -rf ~/.cache/google-chrome", check=False)

    print("[*] Descargando e instalando nuevamente la llave GPG oficial de Google...")
    _retry_download(lambda: run_interactive(GPG_KEY_IMPORT_CMD), "descarga de llave GPG de Google")

    print("[*] Configurando el repositorio oficial de Google Chrome...")
    repo_cmd = 'echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" | sudo tee /etc/apt/sources.list.d/google-chrome.list'
    run_interactive(repo_cmd)

    print("[*] Actualizando listas de paquetes de apt e instalando Google Chrome Stable...")
    apt_install(["google-chrome-stable"])

    print("[✓] Google Chrome ha sido eliminado y reinstalado exitosamente.")
    mark_step_completed("fix_chrome")

def _flush_log_to_disk():
    try:
        logger_instance.logfile.flush()
        os.fsync(logger_instance.logfile.fileno())
    except Exception as e:
        print(f"[!] Advertencia: no se pudo forzar el fsync del log ({e}).")

def _force_reboot():

    reboot_cmd = "sudo reboot"
    print(f"[CMD Interactive] {reboot_cmd}")
    try:
        child = pexpect.spawn("bash", ["-c", reboot_cmd], encoding="utf-8", timeout=30)
        child.logfile_read = sys.stdout
        idx = child.expect([
            r"\[sudo\] password for .*:?",
            r"[pP]assword:",
            pexpect.EOF,
            pexpect.TIMEOUT
        ], timeout=30)
        if idx in (0, 1):
            child.sendline(SUDO_PASSWORD)
            child.expect([pexpect.EOF, pexpect.TIMEOUT], timeout=30)
        child.close(force=True)
        print("[✓] Comando de reinicio enviado correctamente (pexpect).")
        return
    except Exception as e:
        print(f"[!] El reinicio via pexpect fallo o la sesion se volvio inestable: {e}")

    print("[*] Reintentando el reinicio via fallback (subprocess + sudo -S)...")
    try:
        subprocess.run(f'echo "{SUDO_PASSWORD}" | sudo -S reboot', shell=True, timeout=30)
        print("[✓] Comando de reinicio enviado correctamente (fallback subprocess).")
        return
    except Exception as e:
        print(f"[!] El fallback por subprocess tambien fallo: {e}")

    print("[*] Ultimo recurso: forzando el reinicio con 'reboot -f'...")
    try:
        subprocess.run(f'echo "{SUDO_PASSWORD}" | sudo -S reboot -f', shell=True, timeout=30)
        print("[✓] Comando de reinicio forzado enviado correctamente ('reboot -f').")
        return
    except Exception as e:
        print_ascii_fail()
        raise RuntimeError(f"No se pudo forzar el reinicio del sistema por ningun metodo: {e}")

def end_config_reboot():
    if is_step_completed("end_config_reboot"):
        print("[=] Paso 'end_config_reboot' ya fue ejecutado previamente. Omitiendo...")
        return

    GREEN = "\033[92m"
    RESET = "\033[0m"

    state = load_state()
    flags = state.get("flags", {})
    completed_steps = [k for k, v in flags.items() if v]

    tross_flags = load_tross_state().get("flags", {})
    completed_steps += [k for k, v in tross_flags.items() if v]

    print(f"\n{GREEN}{'='*60}")
    print("           CONFIGURACION TERMINADA EXITOSAMENTE           ")
    print(f"{'='*60}{RESET}")
    
    print(f"{GREEN}[+] Pasos completados ({len(completed_steps)}):{RESET}")
    for step in completed_steps:
        print(f"{GREEN}    - {step}{RESET}")
    print(f"{GREEN}    - end_config_reboot (En proceso...){RESET}")
    print(f"{GREEN}{'='*60}\n{RESET}")

    mark_step_completed("end_config_reboot")

    timeout = 300
    print(f"\nSe RECOMIENDA reiniciar el sistema ahora antes de continuar.")
    print(f"El sistema se reiniciara automaticamente en {timeout // 60} minutos si no se hace nada.")
    print("Presiona [ENTER] en cualquier momento para CONTINUAR SIN REINICIAR...")

    start_wait = time.time()
    skip_reboot = False
    while (time.time() - start_wait) < timeout:
        remaining = int(timeout - (time.time() - start_wait))
        mins, secs = divmod(remaining, 60)
        sys.stdout.write(
            f"\rReinicio recomendado en {mins}m {secs:02d}s... "
            f"(Presiona ENTER para continuar SIN reiniciar): "
        )
        sys.stdout.flush()

        rlist, _, _ = select.select([sys.stdin], [], [], 1.0)
        if rlist:
            sys.stdin.readline()
            skip_reboot = True
            break

    if skip_reboot:
        print("\n\n[*] Se omitio el reboot recomendado. Continuando sin reiniciar...")
        return

    print("\n\n[*] Forzando el flush del log a disco (sin cerrarlo) antes del reboot...")
    _flush_log_to_disk()

    print("[*] Forzando el reinicio del sistema...")
    _force_reboot()

    print("[*] Cerrando el log de ejecucion...")
    log_final_summary()

if __name__ == "__main__":
    ensure_credentials()
    print("[*] Activando sudo de forma automatica...")
    if _activate_sudo():
        print("[✓] Sudo activado correctamente.")
    else:
        print("[!] No se pudo confirmar la activacion inicial de sudo.")
    set_ID()
    set_network()
    gitconfig_cookie()
    flex_tag()
    run_security_patch()
    validate_and_lego_setup()
    setup_nomachine_yaml()
    ensure_dhcp()
    run_ansible_playbook()
    provisional_dhcp()
    network_plan()
    force_test_network_selection()
    reinstall_goss()
    run_final_abmx_config()
    create_networkmanager_symlink()
    download_python_tools()
    fix_chrome()
    end_config_reboot()
    juniper_config()
    zpe_config()
    vrmu_util_config()
    tross_capture_mac()
    TROSS_CONFIG()
