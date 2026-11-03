// 画质设置（只保存在本地浏览器）：多重采样（MSAA）倍数。
// 菜单舞台和游戏场景都用泛光后期处理：画面先渲染到离屏缓冲，抗锯齿要靠缓冲本身的多重采样。
const KEY = 'bb_msaa';
export const MSAA_OPTIONS = [0, 2, 4, 8]; // 0 = 不开
export const MSAA_DEFAULT = 4;

/** 当前选择的多重采样倍数（显卡不支持时 three.js 会自动降到它支持的最大值） */
export function getMsaa() {
  const raw = localStorage.getItem(KEY);
  const n = Number(raw);
  return raw !== null && MSAA_OPTIONS.includes(n) ? n : MSAA_DEFAULT;
}

export function setMsaa(n) {
  if (MSAA_OPTIONS.includes(n)) localStorage.setItem(KEY, String(n));
}

/** 修改后期处理缓冲的采样数：释放旧缓冲，下一帧按新的采样数重新创建 */
export function applyMsaa(composer, n) {
  for (const rt of [composer.renderTarget1, composer.renderTarget2]) {
    if (rt.samples === n) continue;
    rt.samples = n;
    rt.dispose();
  }
}
