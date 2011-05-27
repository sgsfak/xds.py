@echo off
cd /D "%~dp0"

SET max=3
SET ub_port=9081
SET PORTS=
rem http://ss64.com/nt/for.html
FOR /L %%I IN (1,1,%max%) DO (call :s_do_sums %%I)
GOTO :eof

:s_do_sums
 set ub="run_ub.bat -p %ub_port% -k %1% -m %max%"
 set PORTS=%PORTS% -n %1
 echo %PORTS%
 set /a ub_port+=2
 echo %ub%
 GOTO :eof

rem start run_ub.bat -p 9081 -k 0 -m 3
rem start run_ub.bat -p 9083 -k 1 -m 3
rem start run_ub.bat -p 9085 -k 2 -m 3
rem start run_xds.bat -n 9082 -n 9084 -n 9086

