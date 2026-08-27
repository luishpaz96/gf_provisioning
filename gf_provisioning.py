#!/usr/bin/env python3
import json
import os
import sys
import subprocess
import re
import pexpect
import time
import select
import atexit

# ==============================================================================
# CONFIGURACIÓN DE LOGGING Y TIEMPO TRASCURRIDO
# ==============================================================================
START_TIME = time.time()
LOG_FILE_PATH = "provisioning_execution.log"

class DualLogger:
    """Duplica la salida estándar (stdout) y de error (stderr) hacia la terminal y un archivo de log."""
    def __init__(self, filepath):
        self.terminal = sys.stdout
        self.logfile = open(filepath, "a", encoding="utf-8")

    def write(self, message):
        self.terminal.write(message)
        self.logfile.write(message)
        self.flush()

    def flush(self):
        self.terminal.flush()
        self.logfile.flush()

    def close(self):
        if self.logfile and not self.logfile.closed:
            self.logfile.flush()
            os.fsync(self.logfile.fileno())  # Fuerza la escritura física en disco
            self.logfile.close()

# Redireccionamos stdout y stderr desde el inicio
logger_instance = DualLogger(LOG_FILE_PATH)
sys.stdout = logger_instance
sys.stderr = logger_instance

def log_final_summary():
    """Calcula el tiempo transcurrido y escribe el resumen final en el log antes de salir o reiniciar."""
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

# Garantiza que el resumen y cierre de archivo se ejecuten siempre (falle o termine normal)
atexit.register(log_final_summary)

# ==============================================================================
# VARIABLES GLOBALES
# ==============================================================================
STATE_FILE = "provisioning_state.json"
SUDO_PASSWORD = "55eed35fba"
VAULT_PASSWORD = r"/!X6i8n0+cxK$v3m4tQ-"
DEFAULT_NOMACHINE_URL = "https://download.nomachine.com/download/9.8/Linux/nomachine_9.8.2_1_amd64.deb"

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

def print_ascii_fail():
    red_code = "\033[91m\033[1m"
    reset_code = "\033[0m"
    banner = r"""
================================================================================

  FFFFFFFFFFFFFFFFFFFFFF     AAA               IIIIIIIIII LLLLLLLLL             
  F::::::::::::::::::::F    A:::A              I::::::::I L::::::::L            
  F::::::::::::::::::::F   A:::::A             I::::::::I L::::::::L            
  FF::::::FFFFFFFFF:::F  A:::::::A            II::::::II LL:::::::LL            
    F:::::F       FFFFFF A:::::A:::::A            I::::I     L::::L             
    F:::::F             A:::::A A:::::A           I::::I     L::::L             
    F::::::FFFFFFFFFF  A:::::A   A:::::A          I::::I     L::::L             
    F:::::::::::::::F A:::::A     A:::::A         I::::I     L::::L             
    F::::::FFFFFFFFFF A:::::AAAAAAAAA:::::A        I::::I     L::::L             
    F:::::F          A::::::::::::::::::::A       I::::I     L::::L             
    F:::::F         A:::::AAAAAAAAAAAAA:::::A      I::::I     L::::L             
    F:::::F        A:::::A             A:::::A     I::::I     L::::L      FFFFFF 
  FF:::::::FF     A:::::A               A:::::A  II::::::II LL:::::::LLLLLL::::L 
  F::::::::F     A:::::A                 A:::::A I::::::::I L::::::::::::::::::L 
  F::::::::F    A:::::A                   A:::::AI::::::::I L::::::::::::::::::L 
  FFFFFFFFFF   AAAAAAA                     AAAAAAAIIIIIIIIIILLLLLLLLLLLLLLLLLLLL 

================================================================================
    """
    print(f"{red_code}{banner}{reset_code}")
    print(f"{red_code}[!] ATENCION OPERADOR: Ansible reporto tareas FALLIDAS (failed > 0).{reset_code}")
    print(f"{red_code}[!] Por favor, revisa el log superior para hacer debug.{reset_code}\n")

def fix_state_file_permissions():
    if os.path.exists(STATE_FILE):
        sudo_user = os.environ.get('SUDO_USER', 'testusr')
        subprocess.run(f"sudo chown {sudo_user}:{sudo_user} {STATE_FILE}", shell=True, stderr=subprocess.DEVNULL)

def load_state():
    fix_state_file_permissions()
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {"flags": {}, "config": {}}

def save_state(state):
    fix_state_file_permissions()
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=4)

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

def run_command(cmd, check=True):
    print(f"[CMD] {cmd}")
    res = subprocess.run(cmd, shell=True)
    if check and res.returncode != 0:
        raise RuntimeError(f"Error ejecutando comando: {cmd}")
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
    run_interactive(
        "wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | sudo gpg --dearmor --yes -o /etc/apt/trusted.gpg.d/google-chrome.gpg"
    )

    run_interactive("sudo apt update")
    run_interactive("sudo apt-get update")

    pkgs_cmd = "sudo apt install openssh-server net-tools git sssd sssd-tools libpam-sss libnss-sss python3-pip -y"
    run_interactive(pkgs_cmd)

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

def run_scp_from_mirror(remote_path, local_destination):
    mirror_ip = "172.24.125.2"
    mirror_pass = "google123"
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
            child.sendline(mirror_pass)
        elif idx == 2:
            break
        elif idx == 3:
            child.close()
            raise RuntimeError(f"Timeout copiando {remote_path} desde el Git Mirror.")

    child.close()
    if child.exitstatus != 0:
        raise RuntimeError(f"Error transfiriendo {remote_path} desde el Git Mirror.")

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

def run_ansible_playbook():
    if is_step_completed("run_ansible_playbook"):
        print("[=] Paso 'run_ansible_playbook' ya fue ejecutado previamente. Omitiendo...")
        return

    print("--- PASO 8: Ejecucion de Ansible Playbook ---")
    state = load_state()
    hostname = state.get("config", {}).get("hostname")

    if not hostname:
        raise RuntimeError("No se encontro el hostname en la configuracion. Asegurate de correr 'set_ID' primero.")

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

    failed_match = re.search(r"failed=(\d+)", output_buffer)
    if failed_match:
        failed_count = int(failed_match.group(1))
        if failed_count > 0:
            print_ascii_fail()
            raise RuntimeError(f"Ansible Playbook finalizo con {failed_count} tarea(s) fallida(s).")

    if child.exitstatus != 0:
        print_ascii_fail()
        raise RuntimeError(f"Error en ejecucion de ansible-playbook (Exit code: {child.exitstatus})")

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

    print("[*] Limpiando archivos goss anteriores...")
    run_command("rm -f goss*", check=False)

    print("[*] Instalando Goss de forma automatizada...")
    goss_install_cmd = "curl -fsSL https://goss.rocks/install | sudo sh"
    run_interactive(goss_install_cmd)

    print("[*] Corrigiendo ownership de /home/testusr/.local...")
    fix_local_dir_cmd = f"sudo chown -R {sudo_user}:{sudo_user} /home/{sudo_user}/.local"
    run_interactive(fix_local_dir_cmd)

    mirror_ip = "172.24.125.2"
    mirror_pass = "google123"

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
            child_copy.sendline(mirror_pass)
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
            child_ansible.sendline(mirror_pass)
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
    apt_cmd = "sudo apt update && sudo apt install -y libsss-sudo gnome-control-center"
    run_interactive(apt_cmd)

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
            print_ascii_fail()
            raise RuntimeError(f"Error descargando {filename} por SCP (Exit code: {child.exitstatus})")

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
    run_interactive(
        "wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | sudo gpg --dearmor --yes -o /etc/apt/trusted.gpg.d/google-chrome.gpg"
    )

    print("[*] Configurando el repositorio oficial de Google Chrome...")
    repo_cmd = 'echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" | sudo tee /etc/apt/sources.list.d/google-chrome.list'
    run_interactive(repo_cmd)

    print("[*] Actualizando listas de paquetes de apt...")
    run_interactive("sudo apt-get update")

    print("[*] Instalando Google Chrome Stable...")
    run_interactive("sudo apt-get install google-chrome-stable -y")

    print("[✓] Google Chrome ha sido eliminado y reinstalado exitosamente.")
    mark_step_completed("fix_chrome")

def end_config_reboot():
    if is_step_completed("end_config_reboot"):
        print("[=] Paso 'end_config_reboot' ya fue ejecutado previamente. Omitiendo...")
        return

    GREEN = "\033[92m"
    RESET = "\033[0m"

    state = load_state()
    flags = state.get("flags", {})
    completed_steps = [k for k, v in flags.items() if v]

    print(f"\n{GREEN}{'='*60}")
    print("           CONFIGURACION TERMINADA EXITOSAMENTE           ")
    print(f"{'='*60}{RESET}")
    
    print(f"{GREEN}[+] Pasos completados ({len(completed_steps)}):{RESET}")
    for step in completed_steps:
        print(f"{GREEN}    - {step}{RESET}")
    print(f"{GREEN}    - end_config_reboot (En proceso...){RESET}")
    print(f"{GREEN}{'='*60}\n{RESET}")

    mark_step_completed("end_config_reboot")

    timeout = 60
    print(f"El sistema se reiniciara automaticamente en {timeout} segundos.")
    print("Presiona [ENTER] para reiniciar inmediatamente...")

    start_wait = time.time()
    while (time.time() - start_wait) < timeout:
        remaining = int(timeout - (time.time() - start_wait))
        sys.stdout.write(f"\rReiniciando en {remaining}s... (Presiona ENTER para adelantar): ")
        sys.stdout.flush()

        rlist, _, _ = select.select([sys.stdin], [], [], 1.0)
        if rlist:
            sys.stdin.readline()
            break

    print("\n\n[*] Forzando cierre del log a disco antes del reboot...")
    log_final_summary()

    print("[*] Iniciando reinicio del sistema...")
    run_interactive("sudo reboot")

if __name__ == "__main__":
    set_ID()
    set_network()
    gitconfig_cookie()
    flex_tag()
    run_security_patch()
    validate_and_lego_setup()
    setup_nomachine_yaml()
    provisional_dhcp()
    run_ansible_playbook()
    run_final_abmx_config()
    create_networkmanager_symlink()
    network_plan()
    download_python_tools()
    fix_chrome()
    end_config_reboot()