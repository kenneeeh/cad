"""Native role permissions and zero-simulation MCP discovery."""
import asyncio
import ast
import json
import os
from pathlib import Path
import sys
import re
import unittest
import yaml
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
LLM = REPO / 'llm'


class TestMultiAgent(unittest.TestCase):
    def test_native_roles_restrict_specialist_tools(self):
        folder = LLM / '.agents'
        self.assertEqual({p.stem for p in (folder / 'agents').glob('*.md')},
                         {'coordinator', 'circuit-sizing-specialist'})
        for path in (folder / 'agents').glob('*.md'):
            config = yaml.safe_load(path.read_text().split('---')[1])
            self.assertEqual(config['model'], 'inherit')
            if path.stem == 'coordinator':
                self.assertTrue(config['inheritMcp'])
            else:
                self.assertIs(config['inheritMcp'], False)
                self.assertEqual(config['tools'], [])
                self.assertFalse(config['mainAgent'])
                for skill in config['skills']:
                    self.assertTrue((folder / skill / 'SKILL.md').exists())

    def test_prompt_uses_one_hypothesis_without_telemetry_schema(self):
        prompt = (LLM / 'experiment.md').read_text()
        self.assertIn('{{budget}}', prompt)
        self.assertIn('{{start}}', prompt)
        self.assertIn('{{workflow}}', prompt)
        self.assertIn('circuit-sizing-specialist', prompt)

    def test_documented_calls_match_existing_tool_arguments(self):
        source = ast.parse((LLM / 'mcp_server.py').read_text())
        tools = {node.name: node for node in source.body
                 if isinstance(node, ast.FunctionDef) and node.decorator_list}
        seen = set()
        pattern = r'\b(' + '|'.join(tools) + r')\(([^)]*)\)'
        for path in (LLM / '.agents/agents/coordinator.md', LLM / 'experiment.md', LLM / 'GEMINI.md'):
            for name, arguments in re.findall(pattern, path.read_text()):
                call = ast.parse(f'{name}({arguments})', mode='eval').body
                self.assertFalse(call.args, (path, name))
                supplied = {keyword.arg for keyword in call.keywords}
                signature = tools[name].args
                allowed = [arg.arg for arg in signature.args]
                required = set(allowed[:len(allowed) - len(signature.defaults)])
                self.assertTrue(required <= supplied <= set(allowed), (path, name, supplied))
                seen.add(name)
        self.assertEqual(seen, set(tools))

    def test_stdio_discovery_and_budget_zero(self):
        asyncio.run(self.discovery())

    async def discovery(self):
        config = StdioServerParameters(command=sys.executable, args=['-B', str(LLM / 'mcp_server.py')],
            env={**os.environ, 'CAD_MAX_SIMULATIONS': '0', 'PYTHONDONTWRITEBYTECODE': '1',
                 'CAD_RUNS_DIR': str(HERE / 'artifacts/llm_simple/stdio')})
        async with stdio_client(config) as streams:
            async with ClientSession(*streams) as client:
                await client.initialize()
                tools = {t.name: t for t in (await client.list_tools()).tools}
                self.assertEqual(set(tools), {'simulate_design', 'evaluate_candidate', 'get_problem', 'get_candidates',
                                             'probe_parameters', 'warmup', 'train'})
                self.assertEqual(set(tools['simulate_design'].input_schema['properties']), {'parameters', 'hypothesis'})
                parameters = json.loads((LLM / 'initial_design.json').read_text())
                result = (await client.call_tool('simulate_design', {'parameters': parameters})).structured_content
                self.assertEqual(result['simulation_count'], 0)
                self.assertIn('budget', result['error'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
