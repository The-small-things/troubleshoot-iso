# Start the troubleshooter once, automatically, on the first console.
if [ "$(tty)" = /dev/tty1 ] && [ ! -e /run/troubleshoot.started ]; then
    touch /run/troubleshoot.started
    /usr/local/bin/troubleshoot-session
    echo
    echo "You are at the command line of the Hardware Troubleshooter live system."
    echo "  troubleshoot-session   start the troubleshooter again"
    echo "  troubleshoot --text    text-mode version"
    echo "  poweroff / reboot      turn off or restart the computer"
    echo
fi
[ -f ~/.bashrc ] && . ~/.bashrc
