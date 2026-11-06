# 声明 / Notice

## 非官方粉丝作品

桌面摸鱼（DeskPond，曾用名「摸鱼钓鱼 / MoyuFishing」）是一个非官方、非商业的粉丝作品，与 ConcernedApe 及《星露谷物语》
(Stardew Valley) 官方没有任何关联，也未获其认可。
"Stardew Valley" 及其中的美术、鱼类数据均归 ConcernedApe LLC 所有。

本仓库**不包含任何游戏美术素材或游戏数据**。和游戏 mod 一样，程序在你本机运行时读取
你自己已购买安装的游戏文件，切好的图片和鱼类表只缓存在你的电脑上
（macOS：`~/Library/Application Support/DeskPond/game_cache/`；Windows：`%APPDATA%\DeskPond\game_cache\`），不会被上传或分发。
请不要把这个缓存目录、`_game_ref/`、`snapshots/` 或任何从游戏中提取的文件提交到仓库或另行发布。
`docs/media/` 里的演示动图是程序运行画面的录屏，只用于在 README 里展示，画面中的游戏美术同样归 ConcernedApe LLC 所有。

钓鱼小游戏的手感参照原版，但物理和鱼的运动是重新写的近似实现，不含游戏代码。
音效：macOS 用系统自带的声音；Windows 用程序自己合成的几段小音效（`src/sounds.py`，同样不含游戏文件）。界面文字用的中文字体也是运行时从你安装的游戏里读取的，同样只缓存在本机。

DeskPond (formerly MoyuFishing) is an unofficial, non-commercial fan project. It is not affiliated
with or endorsed by ConcernedApe. Stardew Valley and all related artwork and data are
property of ConcernedApe LLC. This repository contains no game assets; like a mod,
it reads textures and fish data from your own installed copy of the game at runtime.

## 第三方代码

`src/gamecontent/lzx.py` 移植自 MonoGame 的 `LzxDecoder.cs`（源自 libmspack），
按其原始许可在 LGPL 2.1 与 Microsoft Public License (Ms-PL) 之间双授权，
文件头保留了原版权声明。

- (C) 2003-2004 Stuart Caie
- (C) 2011 Ali Scissons
