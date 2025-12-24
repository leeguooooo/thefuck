from subprocess import Popen, PIPE
from ..utils import DEVNULL, get_installation_version
from .generic import Generic, ShellConfiguration


class Powershell(Generic):
    friendly_name = 'PowerShell'
    _alias_version = get_installation_version()

    def app_alias(self, alias_name):
        return 'function ' + alias_name + ' {\n' \
               '    $env:FUCK_ALIAS_VERSION = "' + self._alias_version + '";\n' \
               '    $history = (Get-History -Count 1).CommandLine;\n' \
               '    if (-not [string]::IsNullOrWhiteSpace($history)) {\n' \
                '        $app = Get-Command fuck -CommandType Application -ErrorAction SilentlyContinue;\n' \
               '        if ($app) {\n' \
               '            $fixed = & $app.Source @args $history;\n' \
               '            if (-not [string]::IsNullOrWhiteSpace($fixed)) {\n' \
               '                if ($fixed.StartsWith("echo")) { $fixed = $fixed.Substring(5); }\n' \
               '                else { iex "$fixed"; }\n' \
               '            }\n' \
               '        }\n' \
               '    }\n' \
               '    [Console]::ResetColor() \n' \
               '}\n'

    def and_(self, *commands):
        return u' -and '.join('({0})'.format(c) for c in commands)

    def how_to_configure(self):
        return ShellConfiguration(
            content=u'iex "$(fuck --alias)"',
            path='$profile',
            reload='. $profile',
            can_configure_automatically=False)

    def alias_refresh_command(self):
        return (u'$app = Get-Command fuck -CommandType Application '
                u'-ErrorAction SilentlyContinue; '
                u'if ($app) { iex "$(& $app.Source --alias)" }')

    def _get_version(self):
        """Returns the version of the current shell"""
        try:
            proc = Popen(
                ['powershell.exe', '$PSVersionTable.PSVersion'],
                stdout=PIPE,
                stderr=DEVNULL)
            version = proc.stdout.read().decode('utf-8').rstrip().split('\n')
            return '.'.join(version[-1].split())
        except IOError:
            proc = Popen(['pwsh', '--version'], stdout=PIPE, stderr=DEVNULL)
            return proc.stdout.read().decode('utf-8').split()[-1]
