use strict;
use warnings;
use Cwd qw(getcwd);
use Errno qw(EACCES EEXIST ENOENT);
use Fcntl qw(O_RDONLY O_DIRECTORY O_NOFOLLOW);
use File::Basename qw(basename dirname);
use File::Temp qw(tempdir);

sub enter_parent {
    my ($parent, $action, $target) = @_;
    chdir("/") or die "Cannot open root for rollback: $!\n";
    # Open each component relative to the already pinned directory.
    for my $component (grep { length } split m{/}, $parent) {
        my $dir;
        unless (sysopen($dir, $component, O_RDONLY | O_DIRECTORY | O_NOFOLLOW)) {
            my $error = "$!";
            return 0 if $! == ENOENT && $action ne "restore";
            if ($! == EACCES && chdir($parent)) {
                # Search-only directories can be entered but cannot be opened for reading.
                # Verify the physical path of the pinned directory before changing anything.
                return 1 if (getcwd() // "") eq $parent;
            }
            die "Cannot $action $target: cannot open parent $parent safely: $error\n";
        }
        chdir($dir) or die "Cannot enter parent $parent for rollback: $!\n";
    }
    return 1;
}

sub restore_backup {
    my ($saved, $name, $target) = @_;
    unless (link($saved, $name)) {
        die "Cannot restore $target: $!\n" if $! == EEXIST;
        # Stage a copy on the destination filesystem before publishing it.
        my $stage = tempdir(".terminal-dotfiles-restore.XXXXXXXX", DIR => ".", CLEANUP => 1);
        my $copy = "$stage/config";
        system("cp", "-a", $saved, $copy) == 0 or die "Cannot stage backup $saved\n";
        link($copy, $name) or die "Cannot restore $target: $!\n";
    }
    unlink($saved) or die "Cannot remove restored backup $saved: $!\n";
}

sub points_to_source {
    my ($link, $source) = @_;
    return 0 unless defined($link);
    my @referent = stat($link);
    my @expected = stat($source);
    return @referent && @expected && $referent[0] == $expected[0] && $referent[1] == $expected[1];
}

sub remove_installed_link {
    my ($name, $source, $target, $parent) = @_;
    return unless points_to_source(readlink($name), $source);

    # Stage the entry before deciding whether it can be deleted.
    my $stage = tempdir(".terminal-dotfiles-rollback.XXXXXXXX", DIR => ".", CLEANUP => 0);
    my $saved = "$stage/entry";
    unless (rename($name, $saved)) {
        my ($missing, $error) = ($! == ENOENT, "$!");
        rmdir($stage) or warn "Cannot remove $parent/$stage: $!\n";
        return if $missing;
        die "Cannot stage $target for rollback: $error\n";
    }

    # Relative symlink targets are interpreted from the original parent.
    my $link = readlink($saved);
    unless (points_to_source($link, $source)) {
        my $restored = defined($link) ? symlink($link, $name) : link($saved, $name);
        unless ($restored) {
            my $error = "$!";
            my $location = getcwd() // $parent;
            die "Cannot return $target: $error; saved at $location/$saved\n";
        }
    }
    unlink($saved) or die "Cannot remove staging entry $parent/$saved: $!\n";
    rmdir($stage) or warn "Cannot remove $parent/$stage: $!\n";
}

my ($action, $target, $source) = @ARGV;
my $parent = dirname($target);
my $name = basename($target);
exit 0 unless enter_parent($parent, $action, $target);

if ($action eq "restore") {
    restore_backup($source, $name, $target);
} elsif ($action eq "remove-link") {
    remove_installed_link($name, $source, $target, $parent);
} elsif ($action eq "remove-directory") {
    rmdir($name);
} else {
    die "Unknown rollback action: $action\n";
}
