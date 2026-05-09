MEMCACHED_INT_IP=$1
echo "Memcached Server Internal IP: ${MEMCACHED_INT_IP}"
sudo apt update
sudo apt install -y memcached libmemcached-tools python3-pip
sudo systemctl status memcached

# replace default memory
sudo sed -i 's/^-m [0-9]*$/-m 1024/' /etc/memcached.conf

# replace localhost
sudo sed -i "s/^-l .*/-l ${MEMCACHED_INT_IP}/" /etc/memcached.conf

# add -t options with default values (will be overridden in benchmarks)
if ! grep -q "^-t" /etc/memcached.conf; then
    echo "-t 8" | sudo tee -a /etc/memcached.conf
fi

sudo systemctl restart memcached
sudo systemctl status memcached
