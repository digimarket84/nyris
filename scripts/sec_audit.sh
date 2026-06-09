#!/usr/bin/env bash
# Audit securite VPS Nyris - LECTURE SEULE (aucune modif). A lancer en sudo.
set +e
line(){ echo; echo "======== $1 ========"; }

line "A. IDENTITE / BOOT / UPTIME"
echo "host=$(hostname) | now=$(date -u +%FT%TZ)"
echo "boot=$(uptime -s) | uptime: $(uptime -p)"
who -b

line "B. CAUSE DU REBOOT (journal)"
journalctl --list-boots --no-pager 2>/dev/null | tail -4
echo "--- derniers evenements avant/au boot ---"
journalctl -k --no-pager 2>/dev/null | grep -iE "reboot|shutdown|power|migrat" | tail -5
last -x reboot shutdown 2>/dev/null | head -6

line "C. CLES HOTE SSH : dates de creation (vs boot)"
ls -l --time-style=full-iso /etc/ssh/ssh_host_*key* 2>/dev/null
for f in /etc/ssh/ssh_host_*key.pub; do echo "$f -> $(ssh-keygen -lf "$f" 2>/dev/null)"; done

line "D. DURCISSEMENT SSHD (doit rester: root no, password no, AllowUsers deploy)"
sshd -T 2>/dev/null | grep -iE "^(permitrootlogin|passwordauthentication|pubkeyauthentication|kbdinteractive|challengeresponse|allowusers|permitemptypasswords|x11forwarding)" | sort
echo "--- drop-ins ---"; ls -l /etc/ssh/sshd_config.d/ 2>/dev/null

line "E. CLES AUTORISEES (deploy + root) - toute cle inattendue = ALERTE"
for u in deploy root; do
  h=$(eval echo ~$u)
  echo "## $u : $h/.ssh/authorized_keys"
  ls -l --time-style=full-iso "$h/.ssh/authorized_keys" 2>/dev/null
  awk '{print "   ["NR"] "$1" "substr($2,1,20)"... "$3}' "$h/.ssh/authorized_keys" 2>/dev/null
done

line "F. COMPTES : UID0 / users recents / sudoers / shadow"
echo "--- comptes UID 0 (doit etre: root seul) ---"; awk -F: '$3==0{print $1}' /etc/passwd
echo "--- comptes avec shell de login ---"; grep -E "/(bash|sh|zsh)$" /etc/passwd
echo "--- /etc/passwd /etc/shadow /etc/sudoers mtimes ---"
ls -l --time-style=full-iso /etc/passwd /etc/shadow /etc/sudoers 2>/dev/null
echo "--- sudoers.d ---"; ls -l /etc/sudoers.d/ 2>/dev/null

line "G. CONNEXIONS : succes recents / echecs / sessions en cours"
echo "--- 12 derniers logins reussis ---"; last -aiF 2>/dev/null | head -12
echo "--- 10 derniers ECHECS (lastb) ---"; lastb -aiF 2>/dev/null | head -10
echo "--- sessions actuelles ---"; w -i 2>/dev/null

line "H. AUTH.LOG : Accepted/Failed (24h) + nouveaux users/cles"
echo "--- Accepted (qui s'est connecte) ---"
grep -hE "Accepted (publickey|password)" /var/log/auth.log 2>/dev/null | tail -12
echo "--- nb Failed/Invalid (volume bruteforce) ---"
grep -hcE "Failed password|Invalid user" /var/log/auth.log 2>/dev/null
echo "--- creations user/group/sudo su recents ---"
grep -hE "useradd|usermod|groupadd|new user|to root|COMMAND=" /var/log/auth.log 2>/dev/null | tail -8

line "I. RESEAU : ports en ecoute + connexions sortantes etablies"
echo "--- LISTEN (attendu: 22, postgres 5432 localhost, 8000 localhost) ---"
ss -tlnp 2>/dev/null
echo "--- ESTABLISHED sortantes (hors localhost) ---"
ss -tnp state established 2>/dev/null | grep -vE "127.0.0.1|::1" | head -15

line "J. PROCESSUS : top CPU (check miner) + noms suspects"
ps -eo pid,user,%cpu,%mem,etimes,comm --sort=-%cpu 2>/dev/null | head -10
echo "--- noms suspects (miner/nc/wget loops/python hors venv) ---"
ps -eo user,comm,args 2>/dev/null | grep -iE "xmrig|minerd|kdevtmpfs|kinsing|\.sh ;|/tmp/|/dev/shm/" | grep -v grep | head

line "K. PERSISTANCE : cron + timers + units recents"
echo "--- crontabs systeme ---"; ls -l /etc/cron.d/ /etc/cron.daily/ 2>/dev/null; cat /etc/crontab 2>/dev/null | grep -vE "^#|^$"
echo "--- crontab par user ---"; for u in root deploy; do echo "[$u]"; crontab -l -u $u 2>/dev/null | grep -vE "^#|^$"; done
echo "--- timers actifs ---"; systemctl list-timers --all --no-pager 2>/dev/null | grep -iE "nyris|NEXT" | head
echo "--- units .service modifiees < 4 jours ---"
find /etc/systemd/system -name "*.service" -mtime -4 -printf "%TY-%Tm-%Td %p\n" 2>/dev/null

line "L. PARE-FEU / FAIL2BAN"
ufw status verbose 2>/dev/null | head -12
echo "--- fail2ban ---"; fail2ban-client status sshd 2>/dev/null | head

line "M. FICHIERS MODIFIES < 3 jours dans zones sensibles"
find /etc /root /home/deploy/.ssh /usr/local/bin -xdev -type f -mtime -3 -printf "%TY-%Tm-%TdT%TH:%TM %p\n" 2>/dev/null | sort | head -40

line "N. APT : installs/upgrades recents"
grep -hE "Install|Upgrade" /var/log/apt/history.log 2>/dev/null | tail -6
ls -l --time-style=full-iso /var/log/apt/history.log 2>/dev/null

line "O. INTEGRITE APP (git : aucune modif locale inattendue)"
cd /srv/nyris/app 2>/dev/null && sudo -u deploy git status --porcelain 2>/dev/null | head && echo "HEAD=$(sudo -u deploy git rev-parse --short HEAD)"

echo; echo "======== FIN AUDIT ========"
