# Use standard xterm terminfo for every SSH destination, including nested SSH.
# Only the child process receives this TERM; the local terminal keeps its value.
function ssh() {
  TERM=xterm-256color command ssh "$@"
}
