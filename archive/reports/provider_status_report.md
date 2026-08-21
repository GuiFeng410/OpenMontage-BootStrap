# OpenMontage Provider 配置报告

> 生成时间：2026-08-04
> 运行命令：`python -c "from tools.tool_registry import registry; import json; registry.discover(); print(json.dumps(registry.provider_menu_summary(), indent=2))"`

## 当前已配置的能力

| 能力 | 已配置 | 总数 | 可用 Provider |
|------|--------|------|--------------|
| video_generation（视频生成） | **1** | 21 | agnes |
| video_post（后期剪辑） | 1 | 9 | ffmpeg |
| tts（配音） | 2 | 7 | dashscope, piper |
| subtitle（字幕） | 2 | 2 | openmontage, remotion |
| screen_capture（录屏） | 2 | 2 | cap, ffmpeg |
| publish（发布） | 1 | 1 | local |
| image_generation（图片生成） | 1 | 12 | pixabay |
| music_search（音乐搜索） | 1 | 2 | pixabay_music |

## 当前未配置的关键能力

| 能力 | 缺失数 | 重要 Provider |
|------|--------|--------------|
| video_generation | **20/21** | kling, seedance, sora, veo, runway, gemini_omni, higgsfield, minimax, grok 等全部未配置 |
| image_generation | **11/12** | flux, google_imagen, grok, comfyui, openai 等未配置 |
| tts | **5/7** | elevenlabs, doubao, google_tts, openai, kling_official 未配置 |
| avatar | 0/5 | sadtalker, wav2lip, kling_avatar 等未配置 |
| music_generation | 0/3 | elevenlabs, google, suno 全部未配置 |
| corpus_population | 0/1 | corpus_builder 未配置（需 opencv+torch+transformers） |
| hyperframes | 0/1 | 未安装（需 Node.js >= 22） |

## Runtime Warnings

- `hyperframes: npm package not resolvable` — 需安装 Node.js >= 22
- `comfyui_video: 需要 ComfyUI 服务器 + 16GB VRAM 推荐` — 本地视频生成需要 GPU

## 核心结论

**当前系统处于"骨架完整但引擎未装"的状态**：
- 管道框架、编排逻辑、测试覆盖全部就绪
- 但核心的 AI 生成引擎（视频/图片/TTS/音乐）几乎全未配置 API Key
- 唯一在线的视频生成是 Agnes 内部模型，图片只有 Pixabay 免费素材
- TTS 有 DashScope（阿里）和 Piper（离线）可用，但缺少 ElevenLabs/Gemini 高质量配音

## 建议优先级

1. **视频生成**：至少配置 1-2 个主力 provider（Kling 官方 / Seedance via fal.ai），才能跑通电商视频 pipeline
2. **图片生成**：配置 Flux via fal.ai，用于商品图/场景图生成
3. **TTS 配音**：配置 ElevenLabs 或 Google TTS，提升旁白质量
4. **Corpus**：配置后才能在本地做素材去重和向量检索
