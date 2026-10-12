# Desktop reconnect launcher

Double-click `Swarm Nodes Reconnect.cmd` on the desktop. It waits for SSH port 22 on both laptops, then opens one Windows Terminal tab per laptop.

- ThinkPad: `thinkpad@192.168.68.71` (uses the existing SSH key)
- ASUS: `chris@192.168.68.70` (prompts for the Linux password unless an SSH key is configured)

The launcher stores no passwords and changes no laptop or Windows settings.
