using System;
using System.Linq;
using System.Threading.Tasks;
using SteamKit2;

// steam-auth: probe Steam licence / depot-key / manifest-code behaviour.
string mode = args.Length > 0 ? args[0] : "help";

var cfg = SteamConfiguration.Create(b => b.WithProtocolTypes(ProtocolTypes.WebSocket));
var client = new SteamClient(cfg);
var manager = new CallbackManager(client);
var user = client.GetHandler<SteamUser>()!;
var apps = client.GetHandler<SteamApps>()!;

manager.Subscribe<SteamClient.ConnectedCallback>(_ => Console.WriteLine("[cm] connected"));
EResult logonResult = EResult.Invalid;
manager.Subscribe<SteamUser.LoggedOnCallback>(cb =>
{
    logonResult = cb.Result;
    Console.WriteLine("[auth] logged on: " + cb.Result + (cb.Result == EResult.OK ? "" : " / " + cb.ExtendedResult));
});
manager.Subscribe<SteamUser.LoggedOffCallback>(cb => Console.WriteLine("[auth] logged off: " + cb.Result));

client.Connect();
_ = Task.Run(() =>
{
    while (true)
    {
        try { manager.RunWaitCallbacks(TimeSpan.FromMilliseconds(250)); }
        catch { break; }
    }
});

var username = Environment.GetEnvironmentVariable("STEAM_USERNAME");
var password = Environment.GetEnvironmentVariable("STEAM_PASSWORD");
var guard = Environment.GetEnvironmentVariable("STEAM_GUARD_CODE") ?? "";
if (!string.IsNullOrWhiteSpace(username) && !string.IsNullOrWhiteSpace(password))
{
    Console.WriteLine("[auth] logging in as " + username);
    user.LogOn(new SteamUser.LogOnDetails
    {
        Username = username,
        Password = password,
        ShouldRememberPassword = false,
        AuthCode = guard,
    });
}
else
{
    Console.WriteLine("[auth] anonymous mode");
    user.LogOnAnonymous();
}

var waitUntil = DateTime.UtcNow.AddSeconds(40);
while (DateTime.UtcNow < waitUntil && logonResult == EResult.Invalid)
{
    await Task.Delay(250);
}
if (logonResult != EResult.OK)
{
    Console.WriteLine("[auth] logon not OK (" + logonResult + "), aborting probe");
    return 2;
}
Console.WriteLine("[auth] ready");
await Task.Delay(500);

try
{
    if (mode == "key")
    {
        var appid = uint.Parse(args[1]);
        var depotid = uint.Parse(args[2]);
        var cb = await apps.GetDepotDecryptionKey(depotid, appid);
        Console.WriteLine("[key] appid=" + appid + " depot=" + depotid + " result=" + cb.Result);
        if (cb.DepotKey is { Length: > 0 })
            Console.WriteLine("  key=" + Convert.ToHexString(cb.DepotKey));
    }
    else if (mode == "manifest")
    {
        var appid = uint.Parse(args[1]);
        var depotid = uint.Parse(args[2]);
        var manifestId = ulong.Parse(args[3]);
        var branch = args.Length > 4 ? args[4] : "public";
        var unified = client.GetHandler<SteamUnifiedMessages>()!;
        var content = unified.CreateService<SteamKit2.Internal.ContentServerDirectory>();
        var request = new SteamKit2.Internal.CContentServerDirectory_GetManifestRequestCode_Request
        {
            app_id = appid,
            depot_id = depotid,
            manifest_id = manifestId,
            app_branch = branch,
            branch_password_hash = "",
        };
        var resp = await content.GetManifestRequestCode(request);
        Console.WriteLine("[manifest] appid=" + appid + " depot=" + depotid + " gid=" + manifestId +
                          " branch=" + branch + " result=" + resp.Result + " code=" + resp.Body?.manifest_request_code);
    }
    else if (mode == "appinfo")
    {
        var appid = uint.Parse(args[1]);
        var request = new SteamApps.PICSRequest(appid);
        var pics = await apps.PICSGetProductInfo(request, null, false);
        foreach (var result in pics.Results)
        {
            if (!result.Apps.ContainsKey(appid)) continue;
            var kv = result.Apps[appid].KeyValues;
            var depots = kv?["depots"];
            if (depots == null || depots.Children == null) { Console.WriteLine("  no depots"); continue; }
            foreach (var child in depots.Children)
            {
                var gid = child["manifests"]?["public"]?["gid"]?.Value ?? "";
                Console.WriteLine("  depot " + child.Name + " gid=" + gid);
            }
        }
    }
    else
    {
        Console.WriteLine("usage: appinfo <appid> | key <appid> <depotid> | manifest <appid> <depotid> <manifestid> [branch]");
    }
}
catch (Exception ex)
{
    Console.WriteLine("[error] " + ex.GetType().Name + ": " + ex.Message);
}

client.Disconnect();
await Task.Delay(800);
return 0;
