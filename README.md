# Phoenix Prime FIX Client Examples 

This repository provides a reference implementation of FIX based trading client connecting to __Phoenix Prime__.
It illustrates how to use the FIX protocol of __Phoenix Prime__ for order execution and to obtain streaming market 
data. 

The FIX client is built on top of the [QuickFix](https://quickfixengine.org) open source FIX library and application framework.

Porting the Client Trading Application to C++, Java or Go is straightforward as QuickFix is available 
for all of these programming languages. Porting it to another FIX library should not be difficult as it illustrates
how to properly setup the different outgoing FIX messages and how to parse the incoming FIX messages. 


## Technical Overview of Phoenix Prime

__Phoenix Prime__ provides order execution through the FIX protocol. It currently supports FIX version 4.4 
with some small custom modifications. 

![Phoenix Single Exchange](docs/single_exchange.png)

On the left hand side the FIX based order execution path is depicted, which optionally can also deliver market
data as FIX messages. 

In order to facilitate cross exchange trading, the client can deploy a strategy multiple times in 
collocation to the desired trading venue. 

![Phoenix Cross Exchange](docs/cross_exchange.png)

Here the same stack as for the single exchange trading is deployed multiple times. The client then can use 
a UDP or TCP connection between the strategies to exchange information and data.

Market data can be obtained through FIX as well. __Phoenix Prime__ also provides a faster and more efficient 
UDP multicast protocol with Simple Binary Encoding (SBE), which is illustrated on the right hand side in the 
above [diagram](docs/single_exchange.png).

Client libraries for C++, Java, Go and Python, implementing a fully functional UDP receiver and a SBE decoder:
  - [C++ SBE Client Library](https://github.com/mtxpt/phx-sbe-receiver-cpp)
  - [Java SBE Client Library](https://github.com/mtxpt/phx-sbe-receiver-java)
  - [Go SBE Client Library](https://github.com/mtxpt/phx-sbe-receiver-go)
  - [Python SBE Client Library](https://github.com/mtxpt/phx-sbe-receiver-py)

The __Phoenix Prime__ market data UDP multicast protocol closely follows the [CME design](https://www.cmegroup.com/confluence/display/EPICSANDBOX/CME+Benchmark+Administration+Premium+-+SBE+UDP+Multicast).
A similar market data service is also offered by [Deribit](https://insights.deribit.com/exchange-updates/launch-of-our-new-multicast-service/).
Lately, Binance also started to experiment with the SBE protocol for market data distribution. 


## FIX Client Quick Start Tutorial

### Connecting to Phoenix FIX Services 

The FIX client needs to provide a session configuration with consists of two parts: 
First part are the account login credentials
``` 
Username=trader
Password=secret
AuthenticateByKey=Y
Account=A1
``` 
The account is required as some client configuration may have multiple __Phoenix Prime__ account configured 
and the order router must know where the order has to be routed to.

Phoenix Prime supports key based authentication by default, which has to be turned on 
by the special field `AuthenticateByKey=Y`. It then creates HMAC based signature from a 
random string and the password

```
    username = self.fix_settings.get(session_id).getString("Username")
    password = self.fix_settings.get(session_id).getString("Password")
    auth_by_key = self.fix_settings.get(session_id).getString("AuthenticateByKey")
    if auth_by_key == "Y":
        random_str = FixBase.get_random_string(8)
        message.setField(fix.RawData(random_str))
        signature = hmac.new(
            password.encode('utf-8'),
            random_str.encode('utf-8'),
            digestmod=hashlib.sha256
        ).digest()
        password = base64.b64encode(signature)
    message.setField(fix.Username(username))
    message.setField(fix.Password(password))    
```

which is then provided as the hashed password field along with the FIX logon message.
Details can be found in the implementation of the method `BaseApp.toAdmin`.

The second part are the FIX specific settings, including the FIX server host IP and socket port
``` 
SenderCompID=trading-firm
TargetCompID=phoenix-pb
SocketConnectPort=1238
SocketConnectHost=127.0.0.1
```

These configurations are usually passed to the FIX application in a
client specific configuration file `client.cfg` in the `[SESSION]` section.

Note that QuickFix also requires in the `[SESSION]` configuration section a reference to a
FIX schema file. __Phoenix Prime__ uses the schema provided in `phx/fix_spec/FIX44.xml`.


### Running a FIX Based Trading Strategy 

The submodule `phx.random_strategy` contains a fully functional FIX application 
implementing the `phx.fix_app.FixStdApp` interface, which provides useful standard
trading functionalities such as

  - Get the security list of the exchange 
  - Subscribe to market data
  - Get instrument meta data from the exchange
  - Get initial position snapshot and wallet balances from the trading account
  - Get initial working orders from the trading account
  - Send requests for new order, order modification and order canceling 
  - Parse FIX messages and represent them with Python objects
  - Keep track of the order book of selected symbols 

It also implements basic OEM services such as tracking the state of orders and positions 
from FIX execution reports. 

The strategy can be configured via the `stragegy.yaml` file.

To run the trading application, run the Bash script `phx/random_trading_app/start.sh` or
the Python script `phx/random_trading_app/main.py`.


## FIX Protocol Pointers

For those who do not know enough about FIX you can learn more here

  - [QuickFix documentation](https://quickfixengine.org/c/documentation/)
  - [Online FIX parser](https://www.esprow.com/fixtools/parser.php)
  - [FIX 4.4 dictionary](https://www.onixs.biz/fix-dictionary/4.4/msgs_by_msg_type.html)
  - [Proof blog](https://medium.com/prooftrading/proof-engineering-fix-gateways-264dcda8be71)

The online FIX parser is particularly useful to understand FIX message strings quickly. 


## Installation 

It is highly recommended to create a new Python environment. The script
`scripts/setup_all.sh` automates the creation of a conda based environment 
with all dependencies installed. Optionally provide the argument `clean` to 
remove existing environment and rebuild all. 

```
scripts/setup_all.sh [clean]
```

Note that `setup_all.sh` also builds a custom QuickFix version for `arm64` architecture. 

By specifying environment variable `ROOT_CERTIFICATE` a root certificate is 
used to configure the global certificate used by `pip3 install` and `conda install`.

Alternatively a Python environment can be created and the `requirements.txt` can 
be installed directly as follows 

``` 
pip3 install -r requirements.txt
```

Note that `requirements.txt` does not install QuickFix for macOS with arm64 architecture
as the current QuickFix version 1.15.1 has some issues and requires a patch. 


## Custom Build QuickFix for arm64 on macOS 

Building QuickFix for Apple arm64 requires a patch. The following script
automates the patch and builds QuickFix for `arm64` from source:

```
scripts/build_quickfix_arm64.sh
```

If you use `setup_all.sh` you don't have to execute this build step as it is handled 
by `setup_all.sh` as well. 


## Installing QuicFix on Windows

The Python QuickFIX bindings also fail to install on Windows. Fortunately, for Windows there are 
[prebuilt wheel packages](https://www.lfd.uci.edu/~gohlke/pythonlibs/#quickfix). 

To setup the Python environment using Conda follow these steps:

  - Install Conda or Miniconda
  - Create a new environment with `conda create --name phx python=3.9`
  - Activate the environment
  - Install all dependencies first `pip install -r requirements.txt` 
  - Download the QuickFix wheel `quickfix‑1.15.1‑cp39‑cp39‑win_amd64.whl`
  - Install the wheel `pip install quickfix‑1.15.1‑cp39‑cp39‑win_amd64.whl`
  - List packages and check if `quickfix 1.15.1` shows up `conda list`

Note that during the execution of `pip install -r requirements.txt` you should first see

```
Ignoring quickfix: markers 'platform_machine != "arm64" and sys_platform != "win32"' don't match your environment
```


## Configure PyCharm

To conveniently work with PyCharm it must be configured to use the proper interpreter.
Set the Python interpreter managed by the Conda package manager in `./opt/conda/`

Lower right corner in PyCharm choose "Python Interpreter". Then

  - `Add New Interpreter` -> `Add Local Interpreter`
  - Choose `Conda Environment` with conda executable `<path to>/opt/conda/condabin/conda` 
  - Click the button `Load Environments`, make sure the radio button `Use existing environment` is selected
  - Choose `dev` and give it optionally another name by editing the interpreter configuration

PyCharm can also be configured for Remote Development. This allows to run the project on the server,
while using PyCharm client.


## Writing Your Own Trading Application 

In order to accelerate the development of FIX based trading application we provide some abstractions 
on top of the plain [QuickFix](http://www.quickfixengine.org/) application interface. Other FIX 
engines can be supported in a similar way.

Note that this library builds on QuickFix which is developed by [quickfixengine.org](http://www.quickfixengine.org/).
Check their [license agreement](http://www.quickfixengine.org/LICENSE) for licensing information.


### QuickFix Application

QuickFix provides an interface `quickfix.Application` which should be implemented by the client 
trading strategy to handle incoming FIX messages and send FIX messages to the FIX server.
The [interface](https://quickfixengine.org/c/documentation/) is as follows:

``` 
class Application(object):
    def onCreate(self, sessionID): 
        """
        Called when quickfix creates a new session. A session comes into and remains 
        in existence for the life of the application. Sessions exist whether or not 
        connected to another FIX counterparty. 
        """
        return 
    def onLogon(self, sessionID):
        """
        Notifies application when a valid logon has been established with FIX counterparty.
        """
        return 
    def onLogout(self, sessionID): 
        """
        Notifies application when an FIX session is no longer online. Can happen 
        during a normal logout exchange, because of a forced termination or a loss of 
        network connection.
        """
        return    
    def toAdmin(self, message, sessionID): 
        """
        Provides applicaiton with a peek at the administrative messages that are being sent 
        from the applicaiton to the FIX counterparty. Within this callback the message can 
        be suitably adjusted.
        """
        return       
    def toApp(self, message, sessionID):
        """
        Callback for application messages that are being sent to a FIX counterparty. If the function 
        throws a DoNotSend exception, the message will not be sent. This is mostly useful if the 
        application has been asked to resend a message such as an order that is no longer relevant 
        for the current market. Messages that are being resent are marked with the PossDupFlag in 
        the header set to true. If a DoNotSend exception is thrown and the flag is set to true, a 
        sequence reset will be sent in place of the message. If it is set to false, the message 
        will simply not be sent.
        """
        return       
    def fromAdmin(self, message, sessionID): 
        """
        Notifies when an administrative message is received by the application. This can be usefull for 
        doing extra validation on logon messages like validating passwords. Throwing a RejectLogon 
        exception will disconnect the FIX counterparty.
        """
        return       
    def fromApp(self, message, sessionID): 
        """
        Receives application level messages. If the application is a buy side FIX client (which is the 
        use case here), this is where the application gets execution reports, trade and position updates 
        and market data updates. If a FieldNotFound exception is thrown, the FIX counterparty will receive 
        a reject indicating a conditionally required field is missing. The Message class will throw this 
        exception when trying to retrieve a missing field, so the application will rarely need the throw 
        this explicitly. The application can also throw an UnsupportedMessageType exception. This will 
        result in the FIX counterparty getting a reject informing them the application cannot process those
        types of messages. An IncorrectTagValue can also be thrown if a field contains a value that is not 
        supported.
        """
        return       
```

It is important to note that these callbacks are executed from QuickFix core, which is a C++ library. 
They can interleave with the main Python thread and a proper locking mechanism has to be used to manage
concurrent access of resources. 


### Basic Application 

The class `phx.fix_app.base.FixBase` implements the above interface `quickfix.Application`.  
It processes all the application level messages, including market data messages and keeps track 
of the order states of working orders and updates positions based on order fills. 
It uses the callbacks of the attached strategy instance to inform the strategy about events, such 
as order books changed, execution reports processed etc. 


### StrategyInterface and StrategyBase

The `StrategyInterface` is the base interface for a client trading strategy. 

Creating a new trading strategy means to implement this interface . It defines various callbacks through 
which the FIX application can forward updates to the strategy. It also should implement the basic
functionality to start and tear down a strategy as well as the core trading loop.

The class `phx.strategy.base.StrategyBase` implements part of the strategy interface 
following a standard workflow to start and execute a client trading strategy along the following steps:

  - Logon to FIX server and wait until successful logon is completed
  - Request security list from exchange and subscribe to market data
  - Request the working orders and position snapshot for the trading account
  - The ready event is fired once all these request are successfully completed
  - Once ready, the main trading loop is started by calling `StrategyInterface.main_trading_loop()`
  - Once `StrategyInterface.main_trading_loop()` is completed all open orders can optionally be cancelled 
    and some collected data is saved to Pandas dataframes

### Strategy Runner

The class `phx.strategy.runner.StrategyRunner` is a convenience wrapper set up the 
environment to run a strategy with a QuickFix application in the back to handle 
order execution and market data. 


### Complete Sample Application

A complete application is provided by `phx.random_strategy.RandomStrategy`.
It randomly executes markets and limit orders and is a good starting basis to 
develop your own FIX based trading application.









