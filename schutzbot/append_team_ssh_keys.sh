#!/bin/bash

for pub_key_file in $(ls team_ssh_keys/); do
  cat "$pub_key_file" | tee -a ~/.ssh/authorized_keys > /dev/null
done
