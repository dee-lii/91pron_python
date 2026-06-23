#!/usr/bin/expect -f
set timeout 120
set host "163.47.132.218"
set user "root"
set password "ghi4jnltiByqNgy0yOeV"

# 打包项目文件
exec tar -czf /tmp/spider-web.tar.gz \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='venv' \
  --exclude='downloads' \
  --exclude='data' \
  --exclude='*.json' \
  --exclude='.DS_Store' \
  --exclude='test_*' \
  --exclude='deploy_remote.sh' \
  --exclude='deploy.sh' \
  --exclude='spider-web.service' \
  --exclude='*.tar.gz' \
  -C /Users/deelii/code/91 \
  *.py templates/ static/ requirements.txt Dockerfile

puts "文件打包完成"

# 上传文件
spawn scp -o StrictHostKeyChecking=no /tmp/spider-web.tar.gz $user@$host:/tmp/
expect {
    "password:" {
        send "$password\r"
        exp_continue
    }
    eof
}
puts "文件上传完成"

# 部署到远程服务器
spawn ssh -o StrictHostKeyChecking=no $user@$host
expect {
    "password:" {
        send "$password\r"
    }
}

expect "# "
send "mkdir -p /opt/spider-web && cd /opt/spider-web && tar -xzf /tmp/spider-web.tar.gz\r"
expect "# "
puts "文件解压完成"

send "curl -fsSL https://get.docker.com | sh\r"
expect {
    "# " { }
    timeout { puts "Docker 安装超时，继续..." }
}
puts "Docker 安装完成"

send "cd /opt/spider-web && docker build -t spider-web .\r"
expect {
    "# " { }
    timeout { puts "Docker 构建超时" }
}
puts "Docker 镜像构建完成"

send "mkdir -p /opt/spider-web/downloads /opt/spider-web/data\r"
expect "# "

send "docker stop spider-web 2>/dev/null; docker rm spider-web 2>/dev/null\r"
expect "# "

send "docker run -d --name spider-web -p 8080:8080 -v /opt/spider-web/downloads:/app/downloads -v /opt/spider-web/data:/app/data --restart always spider-web\r"
expect "# "
puts "Docker 容器启动完成"

send "docker ps\r"
expect "# "

send "exit\r"
expect eof

puts "部署完成！访问 http://$host:8080"
