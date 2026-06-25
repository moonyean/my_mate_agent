import unittest
from agent_core import ToolRequest
from permission import RiskLevel, classify, evaluate


def run_cmd(*args: str) -> ToolRequest:
    return ToolRequest(action="run_command", task="test", reason="test", command=list(args))


def write_file(path: str = "out.txt", content: str = "hello") -> ToolRequest:
    return ToolRequest(action="write_file", task="test", reason="test", file_path=path, content=content)


class ClassifyTests(unittest.TestCase):

    # SAFE
    def test_safe_get_content(self):
        self.assertEqual(classify(run_cmd("powershell", "-Command", "Get-Content file.txt")), RiskLevel.SAFE)

    def test_safe_get_childitem(self):
        self.assertEqual(classify(run_cmd("powershell", "-Command", "Get-ChildItem")), RiskLevel.SAFE)

    def test_safe_ls(self):
        self.assertEqual(classify(run_cmd("ls", "-la")), RiskLevel.SAFE)

    def test_safe_dir(self):
        self.assertEqual(classify(run_cmd("dir")), RiskLevel.SAFE)

    def test_safe_pwd(self):
        self.assertEqual(classify(run_cmd("pwd")), RiskLevel.SAFE)

    def test_safe_echo(self):
        self.assertEqual(classify(run_cmd("echo", "hello")), RiskLevel.SAFE)

    # CONFIRM
    def test_confirm_write_file_action(self):
        self.assertEqual(classify(write_file()), RiskLevel.CONFIRM)

    def test_confirm_set_content(self):
        self.assertEqual(classify(run_cmd("powershell", "-Command", "Set-Content -Path a.txt -Value x")), RiskLevel.CONFIRM)

    def test_confirm_new_item(self):
        self.assertEqual(classify(run_cmd("powershell", "-Command", "New-Item -Type File test.txt")), RiskLevel.CONFIRM)

    def test_confirm_wget(self):
        self.assertEqual(classify(run_cmd("wget", "https://example.com/file.zip")), RiskLevel.CONFIRM)

    def test_confirm_curl(self):
        self.assertEqual(classify(run_cmd("curl", "-O", "https://example.com")), RiskLevel.CONFIRM)

    def test_confirm_invoke_webrequest(self):
        self.assertEqual(classify(run_cmd("powershell", "-Command", "Invoke-WebRequest -Uri https://x.com")), RiskLevel.CONFIRM)

    def test_confirm_mkdir(self):
        self.assertEqual(classify(run_cmd("mkdir", "newfolder")), RiskLevel.CONFIRM)

    # HIGH_RISK
    def test_high_risk_remove_item(self):
        self.assertEqual(classify(run_cmd("powershell", "-Command", "Remove-Item file.txt")), RiskLevel.HIGH_RISK)

    def test_high_risk_rm_rf(self):
        self.assertEqual(classify(run_cmd("rm", "-rf", "/tmp/test")), RiskLevel.HIGH_RISK)

    def test_high_risk_stop_process(self):
        self.assertEqual(classify(run_cmd("powershell", "-Command", "Stop-Process -Name notepad")), RiskLevel.HIGH_RISK)

    def test_high_risk_taskkill(self):
        self.assertEqual(classify(run_cmd("taskkill", "/F", "/IM", "notepad.exe")), RiskLevel.HIGH_RISK)

    def test_high_risk_exe(self):
        self.assertEqual(classify(run_cmd("setup.exe", "/silent")), RiskLevel.HIGH_RISK)

    def test_high_risk_start_process(self):
        self.assertEqual(classify(run_cmd("powershell", "-Command", "Start-Process cmd")), RiskLevel.HIGH_RISK)

    # BLOCK
    def test_block_diskpart(self):
        self.assertEqual(classify(run_cmd("diskpart")), RiskLevel.BLOCK)

    def test_block_format(self):
        self.assertEqual(classify(run_cmd("format", "C:")), RiskLevel.BLOCK)

    def test_block_reg_add(self):
        self.assertEqual(classify(run_cmd("reg", "add", "HKLM\\SOFTWARE\\test")), RiskLevel.BLOCK)

    def test_block_regedit(self):
        self.assertEqual(classify(run_cmd("regedit")), RiskLevel.BLOCK)

    def test_block_set_itemproperty_hklm(self):
        self.assertEqual(classify(run_cmd("powershell", "-Command", "Set-ItemProperty HKLM:\\SOFTWARE\\test -Name x -Value 1")), RiskLevel.BLOCK)

    def test_block_get_credential(self):
        self.assertEqual(classify(run_cmd("powershell", "-Command", "Get-Credential")), RiskLevel.BLOCK)

    def test_block_net_user(self):
        self.assertEqual(classify(run_cmd("net", "user", "admin", "pass")), RiskLevel.BLOCK)

    def test_block_sc_config(self):
        self.assertEqual(classify(run_cmd("sc", "config", "wuauserv", "start=disabled")), RiskLevel.BLOCK)

    def test_block_bcdedit(self):
        self.assertEqual(classify(run_cmd("bcdedit", "/set", "safeboot", "minimal")), RiskLevel.BLOCK)


class EvaluateTests(unittest.TestCase):

    def test_safe_auto_approved(self):
        result = evaluate(run_cmd("ls"))
        self.assertTrue(result.approved)
        self.assertEqual(result.risk, RiskLevel.SAFE)

    def test_block_auto_denied(self):
        result = evaluate(run_cmd("diskpart"))
        self.assertFalse(result.approved)
        self.assertEqual(result.risk, RiskLevel.BLOCK)

    def test_confirm_requires_user_input(self):
        result = evaluate(write_file())
        self.assertFalse(result.approved)
        self.assertEqual(result.risk, RiskLevel.CONFIRM)

    def test_high_risk_requires_user_input(self):
        result = evaluate(run_cmd("powershell", "-Command", "Remove-Item file.txt"))
        self.assertFalse(result.approved)
        self.assertEqual(result.risk, RiskLevel.HIGH_RISK)

    def test_safe_not_auto_approved_when_disabled(self):
        result = evaluate(run_cmd("ls"), auto_approve_safe=False)
        self.assertFalse(result.approved)
        self.assertEqual(result.risk, RiskLevel.SAFE)


if __name__ == "__main__":
    unittest.main()
