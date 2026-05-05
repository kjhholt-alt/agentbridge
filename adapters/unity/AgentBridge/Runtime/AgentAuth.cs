// AgentAuth -- Unity port of the per-launch token persistence.
//
// Writes a 32-char alphanumeric token to:
//   <Application.persistentDataPath>/agentbridge.token
// on adapter start. Clients read it before connecting.

using System;
using System.IO;
using System.Security.Cryptography;
using System.Text;
using UnityEngine;

namespace AgentBridge
{
    public static class AgentAuth
    {
        public const string FileName = "agentbridge.token";
        public const int Length = 32;
        private const string Alphabet =
            "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789";

        public static string EnsureToken()
        {
            string path = TokenPath();
            if (File.Exists(path))
            {
                string existing = File.ReadAllText(path).Trim();
                if (existing.Length >= 16) return existing;
            }
            string token = Generate(Length);
            File.WriteAllText(path, token + "\n", Encoding.UTF8);
            return token;
        }

        public static string TokenPath()
        {
            return Path.Combine(Application.persistentDataPath, FileName);
        }

        private static string Generate(int n)
        {
            var rng = RandomNumberGenerator.Create();
            byte[] buf = new byte[n];
            rng.GetBytes(buf);
            var sb = new StringBuilder(n);
            for (int i = 0; i < n; i++)
            {
                sb.Append(Alphabet[buf[i] % Alphabet.Length]);
            }
            return sb.ToString();
        }

        // Constant-time comparison.
        public static bool ConstantTimeEquals(string a, string b)
        {
            if (a == null || b == null) return false;
            if (a.Length != b.Length)
            {
                // touch every byte of b to avoid early-exit timing leaks
                int dummy = 0;
                foreach (var c in b) dummy ^= c;
                return false;
            }
            int diff = 0;
            for (int i = 0; i < a.Length; i++)
            {
                diff |= a[i] ^ b[i];
            }
            return diff == 0;
        }
    }
}
