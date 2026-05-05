// AgentBridge -- Unity reference adapter for AgentBridge wire protocol v1.0.0.
//
// Attach this MonoBehaviour to a scene-persistent GameObject along
// with AgentStateDump and AgentInputDriver components. Bind only when
// the AGENTBRIDGE=1 environment variable is set on the launching
// process.
//
// Mirrors the behavior of the Godot adapter at:
//   adapters/godot/addons/agentbridge/agent_bridge.gd

using System;
using System.Collections.Generic;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using UnityEngine;

namespace AgentBridge
{
    [DefaultExecutionOrder(-1000)]
    public class AgentBridge : MonoBehaviour
    {
        public const string PROTOCOL_VERSION = "1.0.0";
        public const string SCHEMA_URL = "https://github.com/kjhholt-alt/agentbridge/blob/master/spec/schema/v1";
        public const int RECENT_EVENT_BUF = 256;

        public static readonly string[] SERVER_CAPS = {
            "step", "set_seed", "snapshot_hash", "timescale", "replay",
            "metrics", "actions.bind", "events.subscribe",
        };

        [Tooltip("Force-enable the bridge ignoring the AGENTBRIDGE env var.")]
        public bool ForceEnable = false;
        public int Port = 7777;

        public AgentStateDump StateDump;
        public AgentInputDriver InputDriver;

        private TcpListener _listener;
        private TcpClient _client;
        private NetworkStream _stream;
        private CancellationTokenSource _cts;
        private string _token;
        private string _sessionId = "";
        private bool _handshaked = false;
        private List<string> _grantedCaps = new List<string>();
        private Dictionary<string, bool> _subscriptions = new Dictionary<string, bool>();
        private Queue<Dictionary<string, object>> _events = new Queue<Dictionary<string, object>>();
        private int _eventsDropped;
        private float _sessionStartT;
        private long _commandsTotal;
        private long _actionsTotal;
        private bool _seedSet;
        private long _seed;

        void OnEnable()
        {
            bool envOn = Environment.GetEnvironmentVariable("AGENTBRIDGE") == "1";
            if (!ForceEnable && !envOn) return;
            string envPort = Environment.GetEnvironmentVariable("AGENTBRIDGE_PORT");
            if (!string.IsNullOrEmpty(envPort) && int.TryParse(envPort, out var p))
                Port = p;
            EnsureSiblings();
            _token = AgentAuth.EnsureToken();
            _listener = new TcpListener(IPAddress.Loopback, Port);
            _listener.Start();
            _cts = new CancellationTokenSource();
            _sessionStartT = Time.time;
            Task.Run(() => AcceptLoop(_cts.Token));
            Debug.Log($"[agentbridge] v{PROTOCOL_VERSION} listening on tcp://127.0.0.1:{Port}");
        }

        void OnDisable()
        {
            _cts?.Cancel();
            try { _listener?.Stop(); } catch { /* ignore */ }
            try { _stream?.Close(); } catch { /* ignore */ }
            try { _client?.Close(); } catch { /* ignore */ }
        }

        private void EnsureSiblings()
        {
            if (StateDump == null) StateDump = GetComponent<AgentStateDump>();
            if (StateDump == null)
            {
                StateDump = gameObject.AddComponent<AgentStateDump>();
            }
            if (InputDriver == null) InputDriver = GetComponent<AgentInputDriver>();
            if (InputDriver == null)
            {
                InputDriver = gameObject.AddComponent<AgentInputDriver>();
            }
            InputDriver.RegisterDefaultActions();
        }

        private async Task AcceptLoop(CancellationToken ct)
        {
            while (!ct.IsCancellationRequested)
            {
                try
                {
                    var client = await _listener.AcceptTcpClientAsync();
                    if (_client != null)
                    {
                        try { _stream?.Close(); } catch { /* ignore */ }
                        try { _client?.Close(); } catch { /* ignore */ }
                        InputDriver?.ReleaseAll();
                        _events.Clear();
                    }
                    _client = client;
                    _stream = client.GetStream();
                    _handshaked = false;
                    _grantedCaps.Clear();
                    _subscriptions.Clear();
                    _sessionId = $"sess-{Time.frameCount}-{UnityEngine.Random.Range(0, 1000000)}";
                    PushEvent("client_connected", null);
                    await ServeOne(_stream, ct);
                }
                catch (Exception)
                {
                    if (!ct.IsCancellationRequested) await Task.Delay(50);
                }
            }
        }

        private async Task ServeOne(NetworkStream stream, CancellationToken ct)
        {
            byte[] buf = new byte[8192];
            var sb = new StringBuilder();
            while (!ct.IsCancellationRequested)
            {
                int n;
                try { n = await stream.ReadAsync(buf, 0, buf.Length, ct); }
                catch { break; }
                if (n <= 0) break;
                sb.Append(Encoding.UTF8.GetString(buf, 0, n));
                while (true)
                {
                    string str = sb.ToString();
                    int nl = str.IndexOf('\n');
                    if (nl < 0) break;
                    string line = str.Substring(0, nl).Trim();
                    sb.Remove(0, nl + 1);
                    if (line.Length > 0) HandleLine(line);
                }
            }
        }

        public void PushEvent(string type, Dictionary<string, object> payload)
        {
            var ev = new Dictionary<string, object>();
            if (payload != null) foreach (var kv in payload) ev[kv.Key] = kv.Value;
            ev["type"] = type;
            ev["t"] = Time.time - _sessionStartT;
            if (!string.IsNullOrEmpty(_sessionId)) ev["session_id"] = _sessionId;
            if (_subscriptions.Count > 0 && !_subscriptions.ContainsKey(type)) return;
            _events.Enqueue(ev);
            while (_events.Count > RECENT_EVENT_BUF)
            {
                _events.Dequeue();
                _eventsDropped++;
            }
        }

        private void HandleLine(string line)
        {
            Dictionary<string, object> d;
            try { d = MiniJson.Parse(line); }
            catch { SendErr(2000, "json parse"); return; }
            string cmd = d.TryGetValue("cmd", out var cv) ? cv as string : "";
            if (cmd != "hello" && !_handshaked) { SendErr(1001, "send hello first"); return; }
            _commandsTotal++;
            switch (cmd)
            {
                case "hello":         HandleHello(d); break;
                case "ping":          Send(new Dictionary<string, object>{{"ok", true},{"pong", true}}); break;
                case "state":         HandleState(); break;
                case "action":        HandleAction(d); break;
                case "events":        HandleEvents(); break;
                case "reset":         HandleReset(); break;
                case "quit":          HandleQuit(); break;
                case "capabilities":  Send(new Dictionary<string, object>{{"ok", true},{"capabilities", SERVER_CAPS}}); break;
                case "subscribe":     HandleSubscribe(d, true); break;
                case "unsubscribe":   HandleSubscribe(d, false); break;
                case "set_seed":      HandleSetSeed(d); break;
                case "snapshot_hash": HandleSnapshotHash(); break;
                case "metrics":       HandleMetrics(); break;
                default:              SendErr(1000, $"unknown cmd: {cmd}"); break;
            }
        }

        private void HandleHello(Dictionary<string, object> d)
        {
            string supplied = d.TryGetValue("token", out var tv) ? tv as string : "";
            if (!AgentAuth.ConstantTimeEquals(_token, supplied))
            { SendErr(1002, "token mismatch"); CloseClient(); return; }
            string proto = d.TryGetValue("protocol", out var pv) ? pv as string : "";
            if (!proto.StartsWith("1."))
            { SendErr(1003, $"protocol mismatch {proto}"); CloseClient(); return; }
            _grantedCaps.Clear();
            if (d.TryGetValue("capabilities", out var caps) && caps is List<object> capList)
            {
                foreach (var c in capList)
                {
                    string cs = c as string;
                    if (Array.IndexOf(SERVER_CAPS, cs) >= 0) _grantedCaps.Add(cs);
                }
            }
            _handshaked = true;
            Send(new Dictionary<string, object>{
                {"ok", true},
                {"session_id", _sessionId},
                {"server_caps", SERVER_CAPS},
                {"max_event_buffer", RECENT_EVENT_BUF},
                {"schema_url", SCHEMA_URL},
                {"engine", "unity"},
                {"engine_version", Application.unityVersion},
            });
        }

        private void HandleState()
        {
            if (StateDump == null) { SendErr(3000, "state_dump unavailable"); return; }
            Send(new Dictionary<string, object>{{"ok", true},{"state", StateDump.Snapshot()}});
        }

        private void HandleAction(Dictionary<string, object> d)
        {
            if (InputDriver == null) { SendErr(3000, "input_driver unavailable"); return; }
            string name = d.TryGetValue("name", out var n) ? n as string : "";
            d.TryGetValue("value", out var val);
            var res = InputDriver.ApplyCommand(name, val);
            _actionsTotal++;
            Send(res);
        }

        private void HandleEvents()
        {
            var arr = new List<object>(_events);
            _events.Clear();
            int dropped = _eventsDropped;
            _eventsDropped = 0;
            Send(new Dictionary<string, object>{
                {"ok", true}, {"events", arr}, {"events_dropped", dropped},
            });
        }

        private void HandleReset()
        {
            _events.Clear();
            InputDriver?.ReleaseAll();
            // Note: actual scene reload is engine/game-specific; the
            // adapter just signals readiness.
            Send(new Dictionary<string, object>{{"ok", true}});
        }

        private void HandleQuit()
        {
            Send(new Dictionary<string, object>{{"ok", true}});
            try { _stream?.Close(); } catch { /* ignore */ }
            try { _client?.Close(); } catch { /* ignore */ }
            Application.Quit();
        }

        private void HandleSubscribe(Dictionary<string, object> d, bool on)
        {
            if (!d.TryGetValue("types", out var tv) || !(tv is List<object> types))
            { SendErr(2000, "subscribe needs types[]"); return; }
            foreach (var t in types)
            {
                string s = t as string;
                if (string.IsNullOrEmpty(s)) continue;
                if (on) _subscriptions[s] = true; else _subscriptions.Remove(s);
            }
            var keys = new List<object>(_subscriptions.Keys);
            Send(new Dictionary<string, object>{{"ok", true},{"subscriptions", keys}});
        }

        private void HandleSetSeed(Dictionary<string, object> d)
        {
            if (!_grantedCaps.Contains("set_seed")) { SendErr(1004, "set_seed not granted"); return; }
            long seed = 0;
            if (d.TryGetValue("seed", out var sv)) long.TryParse(sv.ToString(), out seed);
            _seedSet = true; _seed = seed;
            UnityEngine.Random.InitState((int)(seed & 0x7FFFFFFF));
            Send(new Dictionary<string, object>{{"ok", true},{"seed", seed}});
        }

        private void HandleSnapshotHash()
        {
            if (!_grantedCaps.Contains("snapshot_hash")) { SendErr(1004, "snapshot_hash not granted"); return; }
            string h = StateDump?.SnapshotHash() ?? "0000000000000000";
            Send(new Dictionary<string, object>{{"ok", true},{"hash", h}});
        }

        private void HandleMetrics()
        {
            if (!_grantedCaps.Contains("metrics")) { SendErr(1004, "metrics not granted"); return; }
            float elapsed = Mathf.Max(0.0001f, Time.time - _sessionStartT);
            var m = new Dictionary<string, object>{
                {"session_seconds", elapsed},
                {"commands_total", _commandsTotal},
                {"actions_total", _actionsTotal},
                {"actions_per_sec", _actionsTotal / elapsed},
                {"events_emitted", _events.Count},
                {"events_dropped", _eventsDropped},
                {"fps", 1f / Mathf.Max(0.0001f, Time.deltaTime)},
            };
            Send(new Dictionary<string, object>{{"ok", true},{"metrics", m}});
        }

        private void Send(Dictionary<string, object> d)
        {
            if (_stream == null) return;
            string line = MiniJson.Serialize(d) + "\n";
            byte[] bytes = Encoding.UTF8.GetBytes(line);
            try { _stream.Write(bytes, 0, bytes.Length); _stream.Flush(); }
            catch { /* client gone */ }
        }

        private void SendErr(int code, string msg)
        {
            Send(new Dictionary<string, object>{{"ok", false},{"error", msg},{"code", code}});
        }

        private void CloseClient()
        {
            try { _stream?.Close(); } catch { /* ignore */ }
            try { _client?.Close(); } catch { /* ignore */ }
        }
    }

    /// <summary>Tiny JSON parser/serializer to avoid external dependencies.</summary>
    internal static class MiniJson
    {
        public static Dictionary<string, object> Parse(string s)
        {
            int i = 0;
            var v = ParseValue(s, ref i);
            if (v is Dictionary<string, object> d) return d;
            throw new Exception("expected object");
        }

        public static string Serialize(object v)
        {
            var sb = new StringBuilder();
            Write(sb, v);
            return sb.ToString();
        }

        private static object ParseValue(string s, ref int i)
        {
            SkipWs(s, ref i);
            if (i >= s.Length) throw new Exception("unexpected end");
            char c = s[i];
            if (c == '{') return ParseObject(s, ref i);
            if (c == '[') return ParseArray(s, ref i);
            if (c == '"') return ParseString(s, ref i);
            if (c == 't' || c == 'f') return ParseBool(s, ref i);
            if (c == 'n') { i += 4; return null; }
            return ParseNumber(s, ref i);
        }

        private static Dictionary<string, object> ParseObject(string s, ref int i)
        {
            var d = new Dictionary<string, object>();
            i++; // {
            SkipWs(s, ref i);
            if (s[i] == '}') { i++; return d; }
            while (true)
            {
                SkipWs(s, ref i);
                string k = ParseString(s, ref i);
                SkipWs(s, ref i);
                if (s[i] != ':') throw new Exception("expected :");
                i++;
                d[k] = ParseValue(s, ref i);
                SkipWs(s, ref i);
                if (s[i] == ',') { i++; continue; }
                if (s[i] == '}') { i++; return d; }
                throw new Exception("expected , or }");
            }
        }

        private static List<object> ParseArray(string s, ref int i)
        {
            var arr = new List<object>();
            i++;
            SkipWs(s, ref i);
            if (s[i] == ']') { i++; return arr; }
            while (true)
            {
                arr.Add(ParseValue(s, ref i));
                SkipWs(s, ref i);
                if (s[i] == ',') { i++; continue; }
                if (s[i] == ']') { i++; return arr; }
                throw new Exception("expected , or ]");
            }
        }

        private static string ParseString(string s, ref int i)
        {
            if (s[i] != '"') throw new Exception("expected \"");
            i++;
            var sb = new StringBuilder();
            while (s[i] != '"')
            {
                if (s[i] == '\\')
                {
                    i++;
                    char esc = s[i];
                    if (esc == 'n') sb.Append('\n');
                    else if (esc == 't') sb.Append('\t');
                    else if (esc == 'r') sb.Append('\r');
                    else if (esc == '"') sb.Append('"');
                    else if (esc == '\\') sb.Append('\\');
                    else if (esc == '/') sb.Append('/');
                    else if (esc == 'u')
                    {
                        string hex = s.Substring(i+1, 4);
                        sb.Append((char)Convert.ToInt32(hex, 16));
                        i += 4;
                    }
                    else sb.Append(esc);
                    i++;
                    continue;
                }
                sb.Append(s[i]);
                i++;
            }
            i++; // closing "
            return sb.ToString();
        }

        private static bool ParseBool(string s, ref int i)
        {
            if (s[i] == 't') { i += 4; return true; }
            i += 5; return false;
        }

        private static object ParseNumber(string s, ref int i)
        {
            int start = i;
            if (s[i] == '-') i++;
            while (i < s.Length && (char.IsDigit(s[i]) || s[i] == '.' || s[i] == 'e' || s[i] == 'E' || s[i] == '+' || s[i] == '-')) i++;
            string num = s.Substring(start, i - start);
            if (num.Contains('.') || num.Contains('e') || num.Contains('E'))
                return double.Parse(num, System.Globalization.CultureInfo.InvariantCulture);
            if (long.TryParse(num, out var l)) return l;
            return double.Parse(num, System.Globalization.CultureInfo.InvariantCulture);
        }

        private static void SkipWs(string s, ref int i)
        {
            while (i < s.Length && (s[i] == ' ' || s[i] == '\n' || s[i] == '\r' || s[i] == '\t')) i++;
        }

        private static void Write(StringBuilder sb, object v)
        {
            if (v == null) { sb.Append("null"); return; }
            if (v is string str) { WriteString(sb, str); return; }
            if (v is bool b) { sb.Append(b ? "true" : "false"); return; }
            if (v is int || v is long) { sb.Append(v.ToString()); return; }
            if (v is float f) { sb.Append(f.ToString("G", System.Globalization.CultureInfo.InvariantCulture)); return; }
            if (v is double d) { sb.Append(d.ToString("G", System.Globalization.CultureInfo.InvariantCulture)); return; }
            if (v is IDictionary<string, object> dict)
            {
                sb.Append('{');
                bool first = true;
                foreach (var kv in dict)
                {
                    if (!first) sb.Append(',');
                    WriteString(sb, kv.Key);
                    sb.Append(':');
                    Write(sb, kv.Value);
                    first = false;
                }
                sb.Append('}');
                return;
            }
            if (v is System.Collections.IEnumerable en)
            {
                sb.Append('[');
                bool first = true;
                foreach (var item in en)
                {
                    if (!first) sb.Append(',');
                    Write(sb, item);
                    first = false;
                }
                sb.Append(']');
                return;
            }
            WriteString(sb, v.ToString());
        }

        private static void WriteString(StringBuilder sb, string s)
        {
            sb.Append('"');
            foreach (var c in s)
            {
                switch (c)
                {
                    case '"': sb.Append("\\\""); break;
                    case '\\': sb.Append("\\\\"); break;
                    case '\n': sb.Append("\\n"); break;
                    case '\t': sb.Append("\\t"); break;
                    case '\r': sb.Append("\\r"); break;
                    default: sb.Append(c); break;
                }
            }
            sb.Append('"');
        }
    }
}
