#!/bin/bash
tput sgr0; clear

## Load Seedbox Components
source <(wget -qO- https://raw.githubusercontent.com/jerry048/Seedbox-Components/main/seedbox_installation.sh)
# Check if Seedbox Components is successfully loaded
if [ $? -ne 0 ]; then
	echo "Component ~Seedbox Components~ failed to load"
	echo "Check connection with GitHub"
	exit 1
fi

## Load loading animation
source <(wget -qO- https://raw.githubusercontent.com/Silejonu/bash_loading_animations/main/bash_loading_animations.sh)
# Check if bash loading animation is successfully loaded
if [ $? -ne 0 ]; then
	fail "Component ~Bash loading animation~ failed to load"
	fail_exit "Check connection with GitHub"
fi
# Run BLA::stop_loading_animation if the script is interrupted
trap BLA::stop_loading_animation SIGINT

## ============================================================
## Debian 13 补丁：覆盖上游有问题的函数
## ============================================================

# 修复 install_autoremove-torrents_()：
#   1. 移除不存在的 python3-distutils 依赖
#   2. 修正 "su user" 硬编码 bug → "su $username"
#   3. 修正 /home/user/ 硬编码路径 → /home/$username/
#   4. 修正 $HOME/.config.yml → /home/$username/.config.yml
install_autoremove-torrents_() {
	if [[ -z $username ]] || [ -z $password ]; then
		fail "Username or password not set"
		return 1
	fi
	if [[ -z $qb_port ]]; then
		fail "qBittorrent port not set"
		qb_port=8080
	fi
	if [ -f /home/$username/.config.yml ]; then
		fail "Autoremove-torrents already installed"
		return 1
	fi
	## Install Autoremove-torrents
	if [ -z $(which pipx) ]; then
		apt-get install pipx -y
		if [ $? -ne 0 ]; then
			fail "Pipx Installation Failed"
			# Debian 13 兼容方式：用 venv 安装
			apt-get -qqy install python3-setuptools python3-venv python3-full
			python3 -m venv /opt/autoremove-torrents-env
			/opt/autoremove-torrents-env/bin/pip install -q autoremove-torrents
			if [ $? -ne 0 ]; then
				fail "Autoremove-torrents installation failed"
				return 1
			fi
			# 创建可执行包装器，统一路径
			mkdir -p /home/$username/.local/bin
			cat << 'WRAPPER' > /home/$username/.local/bin/autoremove-torrents
#!/bin/bash
exec /opt/autoremove-torrents-env/bin/autoremove-torrents "$@"
WRAPPER
			chmod +x /home/$username/.local/bin/autoremove-torrents
			chown -R $username:$username /home/$username/.local
		else
			su $username -s /bin/sh -c "pipx install autoremove-torrents"
			if [ $? -ne 0 ]; then
				fail "Autoremove-torrents installation failed"
				return 1
			fi
			# 修复原始脚本中 "su user" 的硬编码 bug
			su $username -s /bin/sh -c "pipx ensurepath"
		fi
	else
		su $username -s /bin/sh -c "pipx install autoremove-torrents"
		if [ $? -ne 0 ]; then
			fail "Autoremove-torrents installation failed"
			return 1
		fi
		su $username -s /bin/sh -c "pipx ensurepath"
	fi

	# qBittorrent 配置
	if test -f /usr/bin/qbittorrent-nox; then
		touch /home/$username/.config.yml && chown $username:$username /home/$username/.config.yml
		cat << EOF >>/home/$username/.config.yml
General-qb:
  client: qbittorrent
  host: http://127.0.0.1:$qb_port
  username: $username
  password: $password
  strategies:
    General:
      seeding_time: 3153600000
  delete_data: true
EOF
	fi
	# 修复原始脚本中 $HOME/.config.yml 路径错误
	sed -i 's+127.0.0.1: +127.0.0.1:+g' /home/$username/.config.yml
	mkdir -p /home/$username/.autoremove-torrents/log && chown -R $username /home/$username/.autoremove-torrents
	touch /home/$username/.autoremove-torrents/autoremove-torrents.sh && chown $username:$username /home/$username/.autoremove-torrents/autoremove-torrents.sh
	# 修复原始脚本中 /home/user/ 硬编码路径
	cat << EOF >/home/$username/.autoremove-torrents/autoremove-torrents.sh
#!/bin/bash
while true; do
	/home/$username/.local/bin/autoremove-torrents --conf=/home/$username/.config.yml --log=/home/$username/.autoremove-torrents/log
	sleep 5s
done
EOF
	chmod +x /home/$username/.autoremove-torrents/autoremove-torrents.sh
	touch /etc/systemd/system/autoremove-torrents@.service
	cat << EOF >/etc/systemd/system/autoremove-torrents@.service
[Unit]
Description=autoremove-torrents service
After=syslog.target network-online.target

[Service]
Type=simple
User=$username
Group=$username
ExecStart=/home/$username/.autoremove-torrents/autoremove-torrents.sh

[Install]
WantedBy=multi-user.target
EOF
	systemctl enable autoremove-torrents@$username
	systemctl start autoremove-torrents@$username
	return 0
}

# 修复 install_bbrx_()：
#   Linux 6.x 内核已内置 BBRv3，BBRx DKMS 模块 API 不兼容无法编译
#   直接用 sysctl 启用内置 BBR 即可（kernel_settings_ 函数已写入 sysctl.conf）
install_bbrx_() {
	KERNEL_MAJOR=$(uname -r | cut -d. -f1)
	if [ "$KERNEL_MAJOR" -ge 6 ]; then
		warn "检测到 Linux $KERNEL_MAJOR.x 内核，BBRv3 已内置，无需安装 BBRx DKMS 模块"
		warn "BBRx DKMS 源码与 Linux 6.x 内核 API 不兼容，跳过编译"
		info "BBR 已通过 sysctl 启用（net.ipv4.tcp_congestion_control = bbr）"
		# 确认 sysctl 已应用
		sysctl -w net.core.default_qdisc=fq
		sysctl -w net.ipv4.tcp_congestion_control=bbr
		# 标记为成功（对上层 install_ 包装函数可见）
		return 0
	fi
	# 原始逻辑（Linux 5.x 及更早）
	if [[ -z $OS ]]; then
		if [ -f /etc/os-release ]; then
			. /etc/os-release
			OS=$NAME
		elif type lsb_release >/dev/null 2>&1; then
			OS=$(lsb_release -si)
		elif [ -f /etc/lsb-release ]; then
			. /etc/lsb-release
			OS=$DISTRIB_ID
		elif [ -f /etc/debian_version ]; then
			OS=Debian
		else
			OS=$(uname -s)
		fi
	fi
	if [[ "$OS" =~ "Debian" ]]; then
		if [ $(uname -m) == "x86_64" ]; then
			apt-get -y install linux-image-amd64 linux-headers-amd64
			if [ $? -ne 0 ]; then fail "BBR installation failed"; return 1; fi
		elif [ $(uname -m) == "aarch64" ]; then
			apt-get -y install linux-image-arm64 linux-headers-arm64
			if [ $? -ne 0 ]; then fail "BBR installation failed"; return 1; fi
		fi
	elif [[ "$OS" =~ "Ubuntu" ]]; then
		apt-get -y install linux-image-generic linux-headers-generic
		if [ $? -ne 0 ]; then fail "BBR installation failed"; return 1; fi
	else
		fail "Unsupported OS"; return 1
	fi
	wget https://raw.githubusercontent.com/jerry048/Seedbox-Components/main/BBR/BBRx/BBRx.sh && chmod +x BBRx.sh
	if [ ! -f BBRx.sh ]; then fail "BBR download failed"; return 1; fi
	cat << EOF > /etc/systemd/system/bbrinstall.service
[Unit]
Description=BBRinstall
After=network.target

[Service]
Type=oneshot
ExecStart=/root/BBRx.sh
RemainAfterExit=true

[Install]
WantedBy=multi-user.target
EOF
	systemctl enable bbrinstall.service
	return 0
}

## ============================================================
## 以下为原始 Install.sh 逻辑（仅修改版本检测）
## ============================================================

## Install function
install_() {
info_2 "$2"
BLA::start_loading_animation "${BLA_classic[@]}"
$1 1> /dev/null 2> $3
if [ $? -ne 0 ]; then
	fail_3 "FAIL"
else
	info_3 "Successful"
	export $4=1
fi
BLA::stop_loading_animation
}

## Installation environment Check
info "Checking Installation Environment"
# Check Root Privilege
if [ $(id -u) -ne 0 ]; then
	fail_exit "This script needs root permission to run"
fi

# Linux Distro Version check
if [ -f /etc/os-release ]; then
	. /etc/os-release
	OS=$NAME
	VER=$VERSION_ID
elif type lsb_release >/dev/null 2>&1; then
	OS=$(lsb_release -si)
	VER=$(lsb_release -sr)
elif [ -f /etc/lsb-release ]; then
	. /etc/lsb-release
	OS=$DISTRIB_ID
	VER=$DISTRIB_RELEASE
elif [ -f /etc/debian_version ]; then
	OS=Debian
	VER=$(cat /etc/debian_version)
elif [ -f /etc/SuSe-release ]; then
	OS=SuSe
elif [ -f /etc/redhat-release ]; then
	OS=Redhat
else
	OS=$(uname -s)
	VER=$(uname -r)
fi

if [[ ! "$OS" =~ "Debian" ]] && [[ ! "$OS" =~ "Ubuntu" ]]; then
	fail "$OS $VER is not supported"
	info "Only Debian 10+ and Ubuntu 20.04+ are supported"
	exit 1
fi

if [[ "$OS" =~ "Debian" ]]; then
	# 新增 Debian 13 支持
	if [[ ! "$VER" =~ "10" ]] && [[ ! "$VER" =~ "11" ]] && [[ ! "$VER" =~ "12" ]] && [[ ! "$VER" =~ "13" ]]; then
		fail "$OS $VER is not supported"
		info "Only Debian 10+ are supported"
		exit 1
	fi
fi

if [[ "$OS" =~ "Ubuntu" ]]; then
	if [[ ! "$VER" =~ "20" ]] && [[ ! "$VER" =~ "22" ]] && [[ ! "$VER" =~ "23" ]]; then
		fail "$OS $VER is not supported"
		info "Only Ubuntu 20.04+ is supported"
		exit 1
	fi
fi

## Read input arguments
while getopts "u:p:c:q:l:rbvx3oh" opt; do
  case ${opt} in
	u ) username=${OPTARG} ;;
	p ) password=${OPTARG} ;;
	c )
		cache=${OPTARG}
		while true; do
			if ! [[ "$cache" =~ ^[0-9]+$ ]]; then
				warn "Cache must be a number"
				need_input "Please enter a cache size (in MB):"
				read cache
			else break; fi
		done
		qb_cache=$cache
		;;
	q )
		qb_install=1
		qb_ver=("qBittorrent-${OPTARG}")
		;;
	l )
		lib_ver=("libtorrent-${OPTARG}")
		if [ -z "$qb_ver" ]; then
			warn "You must choose a qBittorrent version for your libtorrent install"
			qb_ver_choose
		fi
		;;
	r ) autoremove_install=1 ;;
	b ) autobrr_install=1 ;;
	v ) vertex_install=1 ;;
	x )
		unset bbrv3_install
		bbrx_install=1
		;;
	3 )
		unset bbrx_install
		bbrv3_install=1
		;;
	o )
		if [[ -n "$qb_install" ]]; then
			need_input "Please enter qBittorrent port:"
			read qb_port
			while true; do
				if ! [[ "$qb_port" =~ ^[0-9]+$ ]]; then
					warn "Port must be a number"
					need_input "Please enter qBittorrent port:"
					read qb_port
				else break; fi
			done
			need_input "Please enter qBittorrent incoming port:"
			read qb_incoming_port
			while true; do
				if ! [[ "$qb_incoming_port" =~ ^[0-9]+$ ]]; then
					warn "Port must be a number"
					need_input "Please enter qBittorrent incoming port:"
					read qb_incoming_port
				else break; fi
			done
		fi
		if [[ -n "$autobrr_install" ]]; then
			need_input "Please enter autobrr port:"
			read autobrr_port
			while true; do
				if ! [[ "$autobrr_port" =~ ^[0-9]+$ ]]; then
					warn "Port must be a number"
					need_input "Please enter autobrr port:"
					read autobrr_port
				else break; fi
			done
		fi
		if [[ -n "$vertex_install" ]]; then
			need_input "Please enter vertex port:"
			read vertex_port
			while true; do
				if ! [[ "$vertex_port" =~ ^[0-9]+$ ]]; then
					warn "Port must be a number"
					need_input "Please enter vertex port:"
					read vertex_port
				else break; fi
			done
		fi
		;;
	h )
		info "Help:"
		info "Usage: ./Install.sh -u <username> -p <password> -c <Cache Size(unit:MiB)> -q <qBittorrent version> -l <libtorrent version> -b -v -r -3 -x -p"
		info "Example: ./Install.sh -u jerry048 -p 1LDw39VOgors -c 3072 -q 4.3.9 -l v1.2.19 -b -v -r -3"
		source <(wget -qO- https://raw.githubusercontent.com/jerry048/Seedbox-Components/main/Torrent%20Clients/qBittorrent/qBittorrent_install.sh)
		seperator
		info "Options:"
		need_input "1. -u : Username"
		need_input "2. -p : Password"
		need_input "3. -c : Cache Size for qBittorrent (unit:MiB)"
		echo -e "\n"
		need_input "4. -q : qBittorrent version"
		need_input "Available qBittorrent versions:"
		tput sgr0; tput setaf 7; tput dim; history -p "${qb_ver_list[@]}"; tput sgr0
		echo -e "\n"
		need_input "5. -l : libtorrent version"
		need_input "Available libtorrent versions:"
		tput sgr0; tput setaf 7; tput dim; history -p "${lib_ver_list[@]}"; tput sgr0
		echo -e "\n"
		need_input "6. -r : Install autoremove-torrents"
		need_input "7. -b : Install autobrr"
		need_input "8. -v : Install vertex"
		need_input "9. -x : Install BBRx (Linux 6.x: 使用内置 BBRv3)"
		need_input "10. -3 : Install BBRv3"
		need_input "11. -o : Specify ports"
		need_input "12. -h : Display help message"
		exit 0
		;;
	\? )
		info "Help:"
		info_2 "Usage: ./Install.sh -u <username> -p <password> -c <Cache Size(unit:MiB)> -q <qBittorrent version> -l <libtorrent version> -b -v -r -3 -x -p"
		exit 1
		;;
	esac
done

# System Update & Dependencies Install
info "Start System Update & Dependencies Install"
update

## Install Seedbox Environment
tput sgr0; clear
info "Start Installing Seedbox Environment"
echo -e "\n"

# qBittorrent
source <(wget -qO- https://raw.githubusercontent.com/jerry048/Seedbox-Components/main/Torrent%20Clients/qBittorrent/qBittorrent_install.sh)
if [ $? -ne 0 ]; then
	fail_exit "Component ~qBittorrent install~ failed to load"
fi

## ============================================================
## Debian 13 补丁：覆盖 install_qBittorrent_()
##   1. 补全 5.0.x / 5.1.x 配置分支（原脚本只到 4.6.x）
##   2. systemd 服务改 Type=simple + 加 --confirm-legal-notice
##      （qBittorrent 5.x 新增强制要求，Type=forking 在 systemd 257 下不稳定）
## ============================================================

install_qBittorrent_(){
	username=$1
	password=$2
	qb_ver=$3
	lib_ver=$4
	qb_cache=$5
	qb_port=$6
	qb_incoming_port=$7

	if pgrep -i -f qbittorrent > /dev/null 2>&1; then
		warn "qBittorrent is running. Stopping it now..."
		systemctl stop "qbittorrent-nox@${username}" 2>/dev/null || true
		pkill -9 -f qbittorrent 2>/dev/null || true
		sleep 2
	fi
	if test -e /usr/bin/qbittorrent-nox; then
		warn "qBittorrent is already installed. Replacing it now..."
		rm /usr/bin/qbittorrent-nox
	fi

	if [[ $(uname -m) == "x86_64" ]]; then
		arch="x86_64"
	elif [[ $(uname -m) == "aarch64" ]]; then
		arch="ARM64"
	else
		warn "Unsupported CPU architecture"
		return 1
	fi

	wget "https://raw.githubusercontent.com/jerry048/Seedbox-Components/main/Torrent%20Clients/qBittorrent/$arch/$qb_ver%20-%20$lib_ver/qbittorrent-nox" -O $HOME/qbittorrent-nox && chmod +x $HOME/qbittorrent-nox
	if [ $? -ne 0 ]; then
		warn "Failed to download qBittorrent-nox executable"
		return 1
	fi
	mv $HOME/qbittorrent-nox /usr/bin/qbittorrent-nox
	mkdir -p /home/$username/qbittorrent/Downloads && chown -R $username:$username /home/$username/qbittorrent/
	mkdir -p /home/$username/.config/qBittorrent && chown $username:$username /home/$username/.config/qBittorrent

	# 服务文件：Type=simple + --confirm-legal-notice（修复 5.x 兼容性）
	if test -e /etc/systemd/system/qbittorrent-nox@.service; then
		rm /etc/systemd/system/qbittorrent-nox@.service
	fi
	touch /etc/systemd/system/qbittorrent-nox@.service
	cat << EOF >/etc/systemd/system/qbittorrent-nox@.service
[Unit]
Description=qBittorrent
After=network.target

[Service]
Type=simple
User=$username
LimitNOFILE=infinity
ExecStart=/usr/bin/qbittorrent-nox --confirm-legal-notice
ExecStop=/usr/bin/killall -w -s 9 /usr/bin/qbittorrent-nox
Restart=on-failure
TimeoutStopSec=20
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
	systemctl enable qbittorrent-nox@$username

	# 检测虚拟化以决定磁盘调优参数
	systemd-detect-virt > /dev/null
	if [ $? -eq 0 ]; then
		aio=8; low_buffer=3072; buffer=15360; buffer_factor=200
	else
		disk_name=$(printf $(lsblk | grep -m1 'disk' | awk '{print $1}'))
		disktype=$(cat /sys/block/$disk_name/queue/rotational)
		if [ "${disktype}" == 0 ]; then
			aio=12; low_buffer=5120; buffer=20480; buffer_factor=250
		else
			aio=4; low_buffer=3072; buffer=10240; buffer_factor=150
		fi
	fi

	# 先写配置再启动：避免 qBittorrent 首次启动覆盖我们的配置

	if [[ "${qb_ver}" =~ "4.1." ]]; then
		md5password=$(echo -n $password | md5sum | awk '{print $1}')
		cat << EOF >/home/$username/.config/qBittorrent/qBittorrent.conf
[BitTorrent]
Session\AsyncIOThreadsCount=$aio
Session\SendBufferLowWatermark=$low_buffer
Session\SendBufferWatermark=$buffer
Session\SendBufferWatermarkFactor=$buffer_factor

[LegalNotice]
Accepted=true

[Network]
Cookies=@Invalid()

[Preferences]
Connection\PortRangeMin=$qb_incoming_port
Downloads\DiskWriteCacheSize=$qb_cache
Downloads\SavePath=/home/$username/qbittorrent/Downloads/
Queueing\QueueingEnabled=false
WebUI\Password_ha1=@ByteArray($md5password)
WebUI\Port=$qb_port
WebUI\Username=$username
EOF
	elif [[ "${qb_ver}" =~ "4.2." ]] || [[ "${qb_ver}" =~ "4.3." ]]; then
		wget "https://raw.githubusercontent.com/jerry048/Seedbox-Components/main/Torrent%20Clients/qBittorrent/$arch/qb_password_gen" -O $HOME/qb_password_gen && chmod +x $HOME/qb_password_gen
		if [ $? -ne 0 ]; then
			warn "Failed to download qb_password_gen"
			rm -rf /home/$username/qbittorrent/Downloads /home/$username/.config/qBittorrent /usr/bin/qbittorrent-nox /etc/systemd/system/qbittorrent-nox@.service
			return 1
		fi
		PBKDF2password=$($HOME/qb_password_gen $password)
		cat << EOF >/home/$username/.config/qBittorrent/qBittorrent.conf
[BitTorrent]
Session\AsyncIOThreadsCount=$aio
Session\SendBufferLowWatermark=$low_buffer
Session\SendBufferWatermark=$buffer
Session\SendBufferWatermarkFactor=$buffer_factor

[LegalNotice]
Accepted=true

[Network]
Cookies=@Invalid()

[Preferences]
Connection\PortRangeMin=$qb_incoming_port
Downloads\DiskWriteCacheSize=$qb_cache
Downloads\SavePath=/home/$username/qbittorrent/Downloads/
Queueing\QueueingEnabled=false
WebUI\Password_PBKDF2="@ByteArray($PBKDF2password)"
WebUI\Port=$qb_port
WebUI\Username=$username
EOF
		rm $HOME/qb_password_gen
	elif [[ "${qb_ver}" =~ "4.4." ]] || [[ "${qb_ver}" =~ "4.5." ]] || [[ "${qb_ver}" =~ "4.6." ]] || \
	     [[ "${qb_ver}" =~ "5.0." ]] || [[ "${qb_ver}" =~ "5.1." ]]; then
		wget "https://raw.githubusercontent.com/jerry048/Seedbox-Components/main/Torrent%20Clients/qBittorrent/$arch/qb_password_gen" -O $HOME/qb_password_gen && chmod +x $HOME/qb_password_gen
		if [ $? -ne 0 ]; then
			warn "Failed to download qb_password_gen"
			rm -rf /home/$username/qbittorrent/Downloads /home/$username/.config/qBittorrent /usr/bin/qbittorrent-nox /etc/systemd/system/qbittorrent-nox@.service
			return 1
		fi
		PBKDF2password=$($HOME/qb_password_gen $password)
		cat << EOF >/home/$username/.config/qBittorrent/qBittorrent.conf
[Application]
MemoryWorkingSetLimit=$qb_cache

[BitTorrent]
Session\AsyncIOThreadsCount=$aio
Session\DefaultSavePath=/home/$username/qbittorrent/Downloads/
Session\DiskCacheSize=$qb_cache
Session\Port=$qb_incoming_port
Session\QueueingSystemEnabled=false
Session\SendBufferLowWatermark=$low_buffer
Session\SendBufferWatermark=$buffer
Session\SendBufferWatermarkFactor=$buffer_factor

[LegalNotice]
Accepted=true

[Network]
Cookies=@Invalid()

[Preferences]
WebUI\Password_PBKDF2="@ByteArray($PBKDF2password)"
WebUI\Port=$qb_port
WebUI\Username=$username
EOF
		rm $HOME/qb_password_gen
	fi
	systemctl start qbittorrent-nox@$username
}


if [[ ! -z "$qb_install" ]]; then
	if [ -z "$username" ]; then
		warn "Username is not specified"
		need_input "Please enter a username:"
		read username
	fi
	if [ -z "$password" ]; then
		# 自动生成随机密码（16位字母数字）
		password=$(head /dev/urandom | tr -dc 'A-Za-z0-9' | head -c16)
		warn "Password not specified, auto-generated: $password"
	fi
	if ! id -u $username > /dev/null 2>&1; then
		useradd -m -s /bin/bash $username
		if [ $? -ne 0 ]; then
			warn "Failed to create user $username"
			return 1
		fi
	fi
	chown -R $username:$username /home/$username
	if [ -z "$cache" ]; then
		warn "Cache is not specified"
		need_input "Please enter a cache size (in MB):"
		read cache
		while true; do
			if ! [[ "$cache" =~ ^[0-9]+$ ]]; then
				warn "Cache must be a number"
				need_input "Please enter a cache size (in MB):"
				read cache
			else break; fi
		done
		qb_cache=$cache
	fi
	if [ -z "$qb_ver" ]; then
		warn "qBittorrent version is not specified"
		qb_ver_check
	fi
	if [ -z "$lib_ver" ]; then
		warn "libtorrent version is not specified"
		lib_ver_check
	fi
	if [ -z "$qb_port" ]; then qb_port=8080; fi
	if [ -z "$qb_incoming_port" ]; then qb_incoming_port=45000; fi

	qb_install_check
	install_ "install_qBittorrent_ $username $password $qb_ver $lib_ver $qb_cache $qb_port $qb_incoming_port" "Installing qBittorrent" "/tmp/qb_error" qb_install_success
fi

# autobrr Install
if [[ ! -z "$autobrr_install" ]]; then
	install_ install_autobrr_ "Installing autobrr" "/tmp/autobrr_error" autobrr_install_success
fi

# vertex Install
if [[ ! -z "$vertex_install" ]]; then
	install_ install_vertex_ "Installing vertex" "/tmp/vertex_error" vertex_install_success
fi

# autoremove-torrents Install
if [[ ! -z "$autoremove_install" ]]; then
	install_ install_autoremove-torrents_ "Installing autoremove-torrents" "/tmp/autoremove_error" autoremove_install_success
fi

seperator

## Tunning
info "Start Doing System Tunning"
install_ tuned_ "Installing tuned" "/tmp/tuned_error" tuned_success
install_ set_txqueuelen_ "Setting txqueuelen" "/tmp/txqueuelen_error" txqueuelen_success
install_ set_file_open_limit_ "Setting File Open Limit" "/tmp/file_open_limit_error" file_open_limit_success

systemd-detect-virt > /dev/null
if [ $? -eq 0 ]; then
	warn "Virtualization is detected, skipping some of the tunning"
	install_ disable_tso_ "Disabling TSO" "/tmp/tso_error" tso_success
else
	install_ set_disk_scheduler_ "Setting Disk Scheduler" "/tmp/disk_scheduler_error" disk_scheduler_success
	install_ set_ring_buffer_ "Setting Ring Buffer" "/tmp/ring_buffer_error" ring_buffer_success
fi
install_ set_initial_congestion_window_ "Setting Initial Congestion Window" "/tmp/initial_congestion_window_error" initial_congestion_window_success
install_ kernel_settings_ "Setting Kernel Settings" "/tmp/kernel_settings_error" kernel_settings_success

# BBRx（Linux 6.x 自动降级为内置 BBRv3）
if [[ ! -z "$bbrx_install" ]]; then
	if [[ ! -z "$(lsmod | grep bbrx)" ]]; then
		warn "Tweaked BBR is already installed"
	else
		install_ install_bbrx_ "Installing BBRx / Enabling built-in BBRv3" "/tmp/bbrx_error" bbrx_install_success
	fi
fi

# BBRv3
if [[ ! -z "$bbrv3_install" ]]; then
	install_ install_bbrv3_ "Installing BBRv3" "/tmp/bbrv3_error" bbrv3_install_success
fi

## Configure Boot Script
info "Start Configuing Boot Script"
touch /root/.boot-script.sh && chmod +x /root/.boot-script.sh
cat << EOF > /root/.boot-script.sh
#!/bin/bash
sleep 120s
source <(wget -qO- https://raw.githubusercontent.com/jerry048/Seedbox-Components/main/seedbox_installation.sh)
if [ \$? -ne 0 ]; then
	exit 1
fi
set_txqueuelen_
systemd-detect-virt > /dev/null
if [ \$? -eq 0 ]; then
	disable_tso_
else
	set_disk_scheduler_
	set_ring_buffer_
fi
set_initial_congestion_window_
EOF
cat << EOF > /etc/systemd/system/boot-script.service
[Unit]
Description=boot-script
After=network.target

[Service]
Type=simple
ExecStart=/root/.boot-script.sh
RemainAfterExit=true

[Install]
WantedBy=multi-user.target
EOF
systemctl enable boot-script.service

seperator

## Finalizing the install
info "Seedbox Installation Complete"
publicip=$(curl -s https://ipinfo.io/ip)

if [[ ! -z "$qb_install_success" ]]; then
	info "qBittorrent installed"
	boring_text "qBittorrent WebUI: http://$publicip:$qb_port"
	boring_text "qBittorrent Username: $username"
	boring_text "qBittorrent Password: $password"
	echo -e "\n"
fi
if [[ ! -z "$autoremove_install_success" ]]; then
	info "autoremove-torrents installed"
	boring_text "Config at /home/$username/.config.yml"
	boring_text "Please read https://autoremove-torrents.readthedocs.io/en/latest/config.html for configuration"
	echo -e "\n"
fi
if [[ ! -z "$autobrr_install_success" ]]; then
	info "autobrr installed"
	boring_text "autobrr WebUI: http://$publicip:$autobrr_port"
	echo -e "\n"
fi
if [[ ! -z "$vertex_install_success" ]]; then
	info "vertex installed"
	boring_text "vertex WebUI: http://$publicip:$vertex_port"
	boring_text "vertex Username: $username"
	boring_text "vertex Password: $password"
	echo -e "\n"
fi
if [[ ! -z "$bbrx_install_success" ]]; then
	KERNEL_MAJOR=$(uname -r | cut -d. -f1)
	if [ "$KERNEL_MAJOR" -ge 6 ]; then
		info "BBRv3 (内置) 已通过 sysctl 启用，无需重启"
	else
		info "BBRx successfully installed, please reboot for it to take effect"
	fi
fi
if [[ ! -z "$bbrv3_install_success" ]]; then
	info "BBRv3 successfully installed, please reboot for it to take effect"
fi

exit 0
