// 各ページ上部に出す操作バー（記録状態＋記録開始/停止＋今すぐ1枚＋セレクタ入力＋SPA検知トグル＋透過トグル）
// のページ側スクリプト。add_init_script でページ遷移・新規タブにも自動適用される。
//
// このファイル全体が「設定オブジェクト C を 1 個受け取る関数式」である。badge.py が読み込み、
// `(<このファイル>)(<設定 JSON>);` の形で呼び出す完成スクリプトを組み立てて add_init_script に
// 渡す。実ファイルなのでエディタ/リンタで構文検査できる。
// 設定は引数で受け取る。**目印の文字列を Python 側が単純置換する形へ戻さないこと** —
// その目印と衝突しうるため、このファイルでテンプレートリテラルの `${...}` 補間が使えなくなる。
// **末尾はセミコロン無しの `}` で
// 終える**こと（badge.py が `(…)(…);` で包むため、ここに `;` があると構文エラーになる）。
//
// バーは Shadow DOM の中に作る。サイト側 CSS はシャドウ境界を越えて中の要素に当たらない
// ため、隔離用の !important を各要素へ付ける必要がなく、見た目は下の <style> 1 枚に集約できる。
// また document.querySelectorAll はシャドウ境界を越えないので、SPA署名・_part.txt 抽出・
// 一致件数の計算にバー要素が紛れ込まない（＝そのための「隠す/戻す」処理も不要）。
//
// 撮影の合図（captureStart/captureEnd）: スクショにはバーが写るので、撮影時は
// バーを上へスライドさせて画面外へ退避してから撮る（意図した動作に見せる）。撮影が
// 終わったら全画面を赤く一瞬フラッシュ（シャッター確定の合図）し、バーを元位置へ戻す。
//
// Python から使う API（固定名を window に生やさない）:
//   Python→ページのヘルパは、起動ごとのランダム名 NS（設定 C の ns）の下へ 1 オブジェクトに
//   まとめ、enumerable:false で公開する。固定名が無いのでサイトから存在検知できない。Python は
//   NS を知っているので window[NS].xxx(...) の形で呼ぶ（badge.py の *_call が式を組み立てる）:
//   - window[NS].applyState(recording, spaOn, selector) : 見た目を現在状態へ更新
//   - window[NS].setCount(n)                             : 撮影カウンタ（本セッション枚数）を更新
//   - window[NS].setHistory(list)                        : セレクタ入力欄の候補（datalist）を更新
//   - window[NS].captureStart()                          : バーを退避し切るまで待つ（撮影直前）
//   - window[NS].captureEnd(ok)                          : シャッターフラッシュ（ok=成功は赤/失敗は琥珀）＋バー復帰（撮影直後）
//   - window[NS].bodyText()                              : バー除外の本文 innerText
//   - window[NS].signature(selector)                    : コンテンツ署名（スモークテスト用）
//   ページ→Python は expose_binding。**その名前はこの JS には書かれておらず、設定 C の bind
//   （badge.py の BIND_* が唯一の出所）から受け取る**。呼び出しは常に
//   callBinding(C.bind.<キー>, tok, …) の形で、参照は BOUND へ退避後に window から消す:
//   - C.bind.getState(tok)        : 描画前に現在状態を取得（枚数 count も含む）
//   - SPA検知はページ側がイベント駆動で行い、落ち着いた変化を検知したら
//     C.bind.spaChanged(tok, sig) を呼んで保存を要求する。
//   - ボタン類は C.bind.toggle(tok)/C.bind.shot(tok)/C.bind.openFolder(tok)/
//     C.bind.spaToggle(tok)/C.bind.setSelector(tok,v)/C.bind.commitSelector(tok,v) を呼ぶ。
//     第1引数の tok は合言葉（設定 C の tok）。Python 側が照合し、一致しない呼び出しは無視する。
//
// 閲覧中サイトからの干渉・検知に対する防御（3 段構え）:
//   1. シャドウは mode:'closed'。host.shadowRoot が null になるため、サイト側スクリプトは
//      バー内部の要素を取得できず、ボタンを click() して記録操作を起こすこともできない。
//      **open へ戻さないこと** — open にすると、tok を知らないサイトでも UI 経由で
//      記録の開始/停止や連写を起こせてしまう。
//   2. expose_binding の参照はこの関数の冒頭で退避する（BOUND）。add_init_script はサイトの JS より
//      先に走るので、ここで掴んだ参照は本物。サイトがバインディングの固定名を自前関数で包んでも、
//      利用者のクリックはその関数を通らないため、第1引数の tok を盗まれない。
//   3. 存在検知の防止: Python→ページのヘルパは固定名でなくランダム名 NS の非列挙プロパティ
//      へ収め、ページ→Python の expose_binding 固定名は退避後に window から削除する。これにより
//      `'__eacApplyState' in window` のような固定名での検知が効かない（バインディング側の
//      固定名も同様。名前は badge.py の BIND_* にあり、この JS には書かれていない）。
(C) => {
  // 表示文言などの設定は Python 側で定義し、C（1個の JSON オブジェクト）でまとめて受け取る。
  // TOK と C.bind（バインディング名）はサブフレームでも先に読む（下の②の掃除に要るため）。
  // expose_binding を呼ぶときの合言葉。各呼び出しの第1引数に付け、Python 側が
  // 照合する。閲覧中サイトのスクリプトが token を知らずに記録操作・連写・セレクタ書き換えを
  // 行っても Python 側で無視される。起動ごとにランダム生成した値が Python から渡ってくる。
  const TOK = C.tok || "";

  // --- expose_binding（Python 側の呼び出し口）の参照を退避し、固定名を window から消す ---
  // add_init_script はサイトの JS より先に実行されるため、ここで掴んだ参照は「本物」である。
  // (1) 参照の退避（BOUND）: これをしないと、サイト側が
  //       const orig = window[<バインディング名>];
  //       window[<バインディング名>] = (t) => { stolen = t; return orig(t); };
  //     のように包んでおくだけで、利用者がボタンを押した瞬間に合言葉（TOK）を盗める。
  //     盗まれれば token 照合は無意味になり、以後は自由に記録操作・連写ができてしまう。
  // (2) 固定名の削除: expose_binding は全フレームの window に固定名で生えるため、サイトは
  //     `'<バインディング名>' in window` でツールの存在を検知できてしまう。
  //     本物の参照を BOUND へ退避したうえで window 上の固定名を消す。以後の呼び出しは BOUND を
  //     使う（callBinding）ので機能は保たれ、サイト JS が動き出す前には固定名が消えている。
  //     iframe にも生える（掃除はフレーム単位）ので、この処理は最上位フレームの早期 return より
  //     前で全フレーム分行う。token 無し（スモーク）ビルドはバインディングを公開せず後から
  //     window へ差し込むため、掃除せず callBinding の実行時フォールバックに任せる。
  //
  //     名前そのものは Python から配られる（C.bind。出所は badge.py の BIND_* 1 箇所）。
  //     **ここに名前を書き戻さないこと**（二重管理になり、片方だけ変えると無言失敗する。
  //     CONTRIBUTING §1-5）。
  const BINDING_NAMES = Object.values(C.bind);
  const BOUND = {};
  BINDING_NAMES.forEach((n) => {
    BOUND[n] = window[n];
    if (TOK) {
      try { delete window[n]; } catch (e) { try { window[n] = undefined; } catch (e2) { /* noop */ } }
    }
  });

  // add_init_script は各 iframe にも注入される。バー本体は最上位フレームだけが作る
  // （iframe の数だけバーが重複表示されるのを防ぐ）。②の掃除は上で全フレーム分済ませてある。
  if (window.top !== window.self) return;

  const ID = C.id;
  const S_ON = C.sOn, S_OFF = C.sOff, L_START = C.lStart, L_STOP = C.lStop, L_SHOT = C.lShot;
  const L_OPEN = C.lOpen, TITLE_OPEN = C.titleOpen;   // 保存先フォルダを開くボタンの文言/説明
  const L_SHOTS = C.lShots;   // 撮影カウンタの文言（"本セッション {n} 枚"）。{n} を枚数に置換する。
  const TITLE_PEEK = C.titlePeek;
  const ARIA_PEEK = C.ariaPeek;   // アイコンのみの透過ボタンのアクセシブル名
  const L_SPA = C.lSpa, PH_SEL = C.phSel, TITLE_SEL = C.titleSel, TITLE_SPA = C.titleSpa;
  // Python から呼ぶページ側ヘルパを収める、起動ごとのランダムな window プロパティ名。
  // 固定名（window.__eacApplyState 等）を生やさないための隠し名。空なら公開しない（テスト用）。
  const NS = C.ns || "";
  // 撮影中だけ隠す要素の CSS セレクタ群（同意バナー・追従ヘッダ対策）。空なら何もしない。
  const HIDE_SEL = Array.isArray(C.hideSel) ? C.hideSel : [];

  // バインディング呼び出しの唯一の入り口。退避済み参照を優先して使う。
  // 退避できていなければ実行時の window を見る（スモークテストのように、バインディングを
  // 公開せず後から差し込む場面のため）。実運用では expose_binding が add_init_script より
  // 先に登録されるので、常に退避済みの本物が使われる。
  // 失敗は握り潰す（未注入・呼び出し不能でもページ操作を壊さない）。
  function callBinding(name) {
    const fn = BOUND[name] || window[name];
    if (typeof fn !== 'function') return undefined;
    try {
      return fn.apply(null, Array.prototype.slice.call(arguments, 1));
    } catch (e) {
      return undefined;
    }
  }

  // --- 撮影演出のタイミング定数（ミリ秒）。ここだけ直せば挙動を調整できる。 ---
  // 対になる CSS 側の時間は、下の <style>（テンプレートリテラル）へ ${...} で差し込む。
  // **JS の定数が唯一の出所。** CSS 側へ数値を手で書き写さないこと。
  const BAR_MOVE_MS = 240;      // バーの退避/復帰アニメーション（CSS: .bar の transition）
  const FLASH_MS = 500;         // シャッターフラッシュのアニメーション長（CSS: .frame.flash）
  const CAP_FALLBACK_MS = BAR_MOVE_MS + 260;  // = 500ms。captureStart: transitionend が来ない場合の保険（退避 240ms を十分に超える上限）
  const FLASH_CLEAR_MS = FLASH_MS + 20;       // = 520ms。captureEnd: シャッターフラッシュ(.flash)を消すまで（CSS の完了を見込み少し長め）
  const BAR_RETURN_MS = 170;    // captureEnd: フラッシュ後にバーを戻すまでの遅延（動きが競合しないよう時間差）

  let recording = false;   // 直近に適用された記録状態（再描画時の復元に使う）
  let spaOn = false;       // 直近に適用された SPA 検知状態
  let selector = "";       // 直近に適用された SPA 検知対象セレクタ（入力欄の値）
  let peekOn = false;      // 透過（半透明）表示中か。下に隠れた内容を確認するための一時状態。
  let shotCount = 0;       // 本セッションで保存できた枚数（Python が本体を持ち、setCount で配る）。
  let selHistory = [];     // 過去に確定したセレクタの候補（datalist）。Python が本体を持ち setHistory で配る。
  let capDepth = 0;        // 進行中の撮影数（重なっても最後の1つで復帰させるための入れ子カウント）
  let frameTimer = null;   // シャッターフラッシュ（.flash クラス）を消すためのタイマー
  let barTimer = null;     // フラッシュ後にバー復帰を少し遅らせるためのタイマー
  let countedSel = null;   // 一致件数を最後に計算したセレクタ（同じ値での再計算を避ける）
  let hiddenEls = [];      // 撮影中に隠した要素と復元用の元 visibility 値

  // --- SPA検知（中身変化のイベント駆動監視） ---
  // 変化は MutationObserver で捉え、SPA_SETTLE_MS のデバウンスで「落ち着いてから」署名を
  // 確定し、前回と違えば Python へ通知する（C.bind.spaChanged）。**Python 側から定期的に
  // 署名を評価するポーリングにしないこと** — 変化があったときだけ計算するので負荷が下がる。
  const SPA_SETTLE_MS = (C.settleMs > 0) ? C.settleMs : 300;   // 変化が止まってから確定するまで
  const SPA_MAX_WAIT_MS = Math.max(SPA_SETTLE_MS * 5, 3000);   // 変化が続く場合でも確定する上限
  let spaLastSig = '';         // 最後に基準/通知した署名
  let spaTimer = null;         // デバウンス用タイマー
  let spaFirstAt = 0;          // 連続変化の起点時刻（上限判定用）
  let spaNavPending = false;   // 直近の遷移（pushState等）を消化中か（基準取り直しのみ・通知しない）
  let spaPrevActive = false;   // 直前の「監視中(spaOn && recording)」状態
  let spaPrevSelector = '';    // 直前のセレクタ（変更検知で基準取り直し）
  let spaObserver = null;      // SPA監視の MutationObserver（監視中のときだけ接続する）

  let host = null;         // ページ側 DOM に置くシャドウホスト（本文取得時の非表示もこれを操作）
  let shadow = null;       // host.shadowRoot（フォーカス判定・要素取得に使う）
  let els = null;          // シャドウ内の主要要素をまとめた参照
  let barObserver = null;  // バー再構築監視の MutationObserver（body 確定後に一度だけ張る）

  // シャドウホストの最小限のスタイル。画面上端いっぱいに敷いて重なり順と当たり判定の
  // 透過だけをインライン !important で固定する（サイト側 CSS に負けない）。見た目は
  // シャドウ内の <style> が受け持つ。中央寄せは内側の flex で行い、ホストには transform を
  // 使わない（transform を持つ要素は position:fixed の子の基準になってしまい、下の全画面
  // フラッシュがホスト内に閉じ込められてしまうため）。
  const HOST_CSS = `
    position:fixed !important;top:0 !important;left:0 !important;right:0 !important;
    z-index:2147483647 !important;margin:0 !important;padding:0 !important;border:0 !important;
    pointer-events:none !important;display:block !important;`;

  // シャドウ内のスタイルと構造。境界で隔離されるので通常の CSS クラスで書ける。
  // 文言（ラベル/プレースホルダ/title）は textContent/属性で後から入れる（HTML へ
  // 直接埋め込まず、日本語・絵文字・引用符のエスケープを気にせずに済ませる）。
  const STYLE = `<style>
    .wrap{display:flex;justify-content:center;align-items:flex-start;padding-top:8px;pointer-events:none;}
    .bar{box-sizing:border-box;height:36px;display:flex;align-items:center;gap:14px;
      margin:0;padding:0 16px;border-radius:8px;pointer-events:none;white-space:nowrap;
      color:#fff;font-family:"Segoe UI",sans-serif;font-size:13px;font-weight:bold;line-height:1;
      box-shadow:0 2px 8px rgba(0,0,0,.4);background:rgba(90,90,90,.92);
      /* 退避/復帰は同じ transition（＝隠す動きと戻る動きを対称に）。少しゆっくりの ease-out。
         透過（peek）で背景を消す/戻すのも滑らかに見せるため background も一緒に遷移させる。
         時間は上の BAR_MOVE_MS から差し込む（JS の待ち時間と CSS を同じ出所にする）。 */
      transition:transform ${BAR_MOVE_MS}ms cubic-bezier(.22,.61,.36,1),background .18s ease;}
    .bar.rec{background:rgba(200,0,0,.92);}
    .bar.idle{background:rgba(90,90,90,.92);}
    /* 撮影時: バーを上端の外まで退避（スクショに写らない）。 */
    .bar.capturing{transform:translateY(-64px);}
    /* 透過表示中: バーの背景を消し、透過ボタン以外を薄くして下のページ内容を確認できるようにする。
       透過ボタン（アイコン）は常にはっきり見せて戻す場所を見失わせない。滑らかに切り替わるよう
       薄くする対象に opacity の transition を付ける。 */
    .status,.btn,.sel-wrap,.spa-wrap{transition:opacity .18s ease;}
    .bar.peek{background:transparent;box-shadow:none;}
    .bar.peek > *:not(.peek-btn){opacity:.16;}
    .status{box-sizing:border-box;flex:0 0 auto;width:84px;height:36px;
      display:inline-flex;align-items:center;justify-content:center;gap:6px;}
    .dot{box-sizing:border-box;flex:0 0 auto;width:9px;height:9px;border-radius:50%;}
    .dot.rec{background:#fff;border:0;}
    .dot.idle{background:transparent;border:2px solid rgba(255,255,255,.85);}
    .label{flex:0 0 auto;}
    /* 撮影カウンタ（本セッション N 枚）。控えめな白字で常時出す。 */
    .shots{flex:0 0 auto;white-space:nowrap;color:rgba(255,255,255,.9);
      font-family:"Segoe UI",sans-serif;font-size:12px;font-weight:normal;line-height:1;}
    .btn{box-sizing:border-box;flex:0 0 auto;height:26px;display:inline-flex;align-items:center;
      justify-content:center;white-space:nowrap;margin:0;padding:0 12px;pointer-events:auto;cursor:pointer;
      border:0;border-radius:5px;background:#fff;color:#b00;
      font-family:"Segoe UI",sans-serif;font-size:12px;font-weight:bold;line-height:1;
      appearance:none;-webkit-appearance:none;}
    /* 透過ボタン: 記録操作(.btn)とは種類が違う「表示ユーティリティ」。枠も背景も持たない
       アイコンだけのボタンにし、ON/OFF はアイコン自体の装飾（目のスラッシュ・色・発光）で表す。 */
    .peek-btn{box-sizing:border-box;flex:0 0 auto;display:inline-flex;align-items:center;justify-content:center;
      width:30px;height:30px;margin:0 0 0 2px;padding:0;pointer-events:auto;cursor:pointer;
      border:0;background:transparent;appearance:none;-webkit-appearance:none;
      color:rgba(255,255,255,.85);transition:color .15s ease,transform .1s ease,filter .15s ease;}
    .peek-btn:hover{color:#fff;transform:scale(1.1);}
    .peek-btn:active{transform:scale(.92);}
    .peek-icon{width:20px;height:20px;display:block;overflow:visible;
      fill:none;stroke:currentColor;stroke-width:2;stroke-linecap:round;stroke-linejoin:round;}
    /* OFF（透過していない＝見ていない）: 目にスラッシュを重ねる。 */
    .peek-icon .eye-slash{transition:opacity .15s ease;}
    /* ON（透過中）: スラッシュを消し、琥珀色＋発光で「見えている」状態を示す。 */
    .peek-btn.on{color:#ffd24d;filter:drop-shadow(0 0 4px rgba(255,200,60,.9));}
    .peek-btn.on .eye-slash{opacity:0;}
    .sel-wrap{box-sizing:border-box;flex:0 0 auto;display:inline-flex;align-items:center;gap:8px;pointer-events:auto;}
    .sel{box-sizing:border-box;flex:0 0 auto;width:180px;height:26px;margin:0;padding:0 8px;pointer-events:auto;
      border:1px solid rgba(255,255,255,.6);border-radius:5px;background:#fff;color:#111;
      font-family:"Segoe UI",sans-serif;font-size:12px;font-weight:normal;line-height:1;
      appearance:none;-webkit-appearance:none;}
    .sel-count{flex:0 0 76px;width:76px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;
      color:rgba(255,255,255,.85);font-family:"Segoe UI",sans-serif;font-size:11px;font-weight:normal;line-height:1;}
    .sel-count.warn{color:#ffd24d;}
    .spa-wrap{box-sizing:border-box;flex:0 0 auto;display:inline-flex;align-items:center;gap:8px;pointer-events:auto;}
    .spa-wrap.disabled{opacity:.45;}
    .spa-label{flex:0 0 auto;white-space:nowrap;color:#fff;
      font-family:"Segoe UI",sans-serif;font-size:12px;font-weight:bold;line-height:1;}
    .spa{box-sizing:border-box;position:relative;flex:0 0 auto;width:50px;height:24px;margin:0;padding:0;
      border:0;border-radius:12px;pointer-events:auto;cursor:pointer;background:rgba(255,255,255,.35);
      appearance:none;-webkit-appearance:none;transition:background .15s ease;}
    .spa.on{background:#7cc243;}
    .spa.off{background:rgba(255,255,255,.35);}
    .spa:disabled{background:rgba(255,255,255,.2);cursor:not-allowed;}
    .spa-text{position:absolute;top:0;height:24px;display:flex;align-items:center;
      color:#fff;font-family:"Segoe UI",sans-serif;font-size:10px;font-weight:bold;line-height:1;pointer-events:none;}
    .spa.on .spa-text{left:8px;right:auto;}
    .spa.off .spa-text{right:7px;left:auto;}
    .spa-knob{position:absolute;top:2px;left:2px;width:20px;height:20px;border-radius:50%;background:#fff;
      box-shadow:0 1px 2px rgba(0,0,0,.35);transition:left .15s ease;pointer-events:none;}
    .spa.on .spa-knob{left:28px;}
    .spa.off .spa-knob{left:2px;}
    /* 撮影完了の合図に使う全画面の赤いシャッターフラッシュ（既定は透明、.flash で発光）。
       ホストに transform が無いので position:fixed はビューポート基準になり全画面に出る。
       枠は付けず、全画面の淡い赤み＋内側から広がる赤いグローだけ。パッと光って引く単発フラッシュ。 */
    .frame{position:fixed;inset:0;
      background:rgba(255,0,0,.10);box-shadow:inset 0 0 90px 14px rgba(255,0,0,.55);
      pointer-events:none;opacity:0;}
    /* 保存失敗時のフラッシュ: 成功（赤）と同じ色だと「撮れた」と誤解を招くので、
       警告色の琥珀へ差し替える。発光アニメーション（.flash）は共通で、色だけを変える。 */
    .frame.fail{background:rgba(255,170,0,.12);box-shadow:inset 0 0 90px 14px rgba(255,150,0,.6);}
    /* 時間は上の FLASH_MS から差し込む（フラッシュを畳む FLASH_CLEAR_MS と同じ出所）。 */
    .frame.flash{animation:eac-shutter ${FLASH_MS}ms ease-out;}
    @keyframes eac-shutter{0%{opacity:0;}9%{opacity:1;}100%{opacity:0;}}
    </style>`;

  // バーの構造。要素間の空白（改行/インデント）は flex/inline-flex コンテナ内では
  // 空白のみのテキストノードとして無視されるため、表示には影響しない。文言は
  // 後から textContent/属性で入れる（HTML への直接埋め込みを避ける）。
  // セレクタ候補の datalist の id はシャドウ内で閉じているのでページ側とは衝突しない
  // （この JS には __eac_ で始まる文字列リテラルを置かない。id 自体はどう名付けても等価）。
  const MARKUP = `
    <div class="wrap"><div class="bar idle" data-eac="bar">
      <span class="status"><span class="dot idle" data-eac="dot"></span><span class="label" data-eac="label"></span></span>
      <button class="btn" data-eac="toggle"></button>
      <button class="btn" data-eac="shot"></button>
      <button class="btn" data-eac="open"></button>
      <span class="shots" data-eac="shots"></span>
      <span class="sel-wrap"><input class="sel" type="text" data-eac="selector" list="sel-history"><datalist id="sel-history" data-eac="history"></datalist><span class="sel-count" data-eac="sel-count"></span></span>
      <span class="spa-wrap" data-eac="spa-wrap"><span class="spa-label" data-eac="spa-label"></span>
        <button class="spa off" role="switch" data-eac="spa"><span class="spa-text" data-eac="spa-text"></span>
        <span class="spa-knob"></span></button></span>
      <button class="peek-btn" data-eac="peek"><svg class="peek-icon" viewBox="0 0 24 24" aria-hidden="true">
        <path d="M1 12s4-7 11-7 11 7 11 7-4 7-11 7-11-7-11-7z"></path>
        <circle cx="12" cy="12" r="3"></circle>
        <line class="eye-slash" x1="3.5" y1="3.5" x2="20.5" y2="20.5"></line></svg></button>
    </div></div>
    <div class="frame" data-eac="frame"></div>`;

  const TEMPLATE = STYLE + MARKUP;

  // 現在状態（記録中/SPA検知/セレクタ）をバーの見た目へ反映する。
  // 見た目の切り替えはすべて CSS クラス（rec/idle・on/off・warn・disabled）の付け外しで行う。
  function apply(r, s, sel) {
    recording = !!r;
    spaOn = !!s;
    if (sel !== undefined && sel !== null) selector = String(sel);

    // SPA監視の基準取り直し（UI とは独立。バー未構築でも動くよう els ガードより前で行う）。
    spaSyncBaseline();

    if (!els) return;

    // 記録中＝赤バー・白丸／待機中＝灰バー・白輪郭の丸。
    els.bar.classList.toggle('rec', recording);
    els.bar.classList.toggle('idle', !recording);
    els.dot.classList.toggle('rec', recording);
    els.dot.classList.toggle('idle', !recording);
    els.label.textContent = recording ? S_ON : S_OFF;
    els.toggle.textContent = recording ? L_STOP : L_START;

    // 透過（peek）表示の反映。記録状態とは独立した見た目だけの状態。
    els.bar.classList.toggle('peek', peekOn);
    els.peek.classList.toggle('on', peekOn);

    // セレクタ入力欄はフォーカス中は書き換えない（タイピングを壊さない）。
    // 非フォーカス時のみ現在値と差があれば同期（別タブでの変更を反映）。
    if (shadow.activeElement !== els.sel && els.sel.value !== selector) els.sel.value = selector;

    // 一致件数フィードバック。セレクタ文字列が変わったときだけ数え直す（apply は記録状態や
    // 枚数の更新でも呼ばれるが、同じセレクタなら件数表示は変わらないので
    // querySelectorAll を無駄打ちしない）。
    const s2 = (selector || '').trim();
    if (s2 !== countedSel) {
      countedSel = s2;
      updateMatchCount(s2);
    }

    // SPA検知トグル: 既定ルート監視により、セレクタ未設定でも操作できる（常に有効）。
    // セレクタを入れればその要素、未入力ならページ主要部（main/article/本文）を監視する。
    els.spa.disabled = false;
    els.spaWrap.classList.remove('disabled');
    els.spa.classList.toggle('on', spaOn);
    els.spa.classList.toggle('off', !spaOn);
    els.spaText.textContent = spaOn ? 'ON' : 'OFF';
    // role="switch" の状態を支援技術へ伝える（見た目のクラス切替と同じ所で反映）。
    els.spa.setAttribute('aria-checked', spaOn ? 'true' : 'false');
  }

  // セレクタ一致件数の表示を更新する。0件/不正はすぐ気づけるよう色を変える（warn クラス）。
  // バーはシャドウ内なので querySelectorAll には紛れ込まない（除外処理は不要）。
  function updateMatchCount(s2) {
    if (!els) return;
    if (!s2) {
      els.selCount.textContent = '';
      els.selCount.classList.remove('warn');
      return;
    }
    try {
      const n = document.querySelectorAll(s2).length;
      els.selCount.textContent = '一致 ' + n + '件';
      els.selCount.classList.toggle('warn', n === 0);
    } catch (e) {
      els.selCount.textContent = '無効な指定';
      els.selCount.classList.add('warn');
    }
  }

  // 撮影カウンタ（本セッション N 枚）の表示を更新する。枚数の本体は Python が持ち、
  // 保存成功のたびに setCount で配られる。バー未構築なら値だけ覚えて描画時に反映する。
  function renderShots() {
    if (els && els.shots) els.shots.textContent = L_SHOTS.replace('{n}', shotCount);
  }

  // Python から枚数を受け取ってバーへ反映する。非数・負値は無視して直近値を保つ
  //（getstate と push が競合しても表示が巻き戻らないようにする）。
  function setShotCount(n) {
    if (typeof n === 'number' && n >= 0) shotCount = n;
    renderShots();
  }

  // セレクタ入力欄の候補（datalist の <option>）を過去の確定値で作り直す。候補の
  // 本体は Python が持ち、セレクタ確定（blur/Enter）のたびに setHistory で全バーへ配られる。
  // バー未構築なら値だけ覚えておき、描画時（build）に反映する。
  function renderHistory() {
    if (!els || !els.history) return;
    while (els.history.firstChild) els.history.removeChild(els.history.firstChild);
    selHistory.forEach((v) => {
      const opt = document.createElement('option');
      opt.value = v;
      els.history.appendChild(opt);
    });
  }

  // Python から候補一覧を受け取って datalist へ反映する。配列以外・非文字列要素は無視する
  // （不正な push が来ても既存候補を壊さない）。
  function setHistory(list) {
    if (Array.isArray(list)) selHistory = list.filter((v) => typeof v === 'string');
    renderHistory();
  }

  // 撮影中だけ hide_selectors 該当要素を隠す。同意バナー・追従ヘッダなどが証跡
  // （スクショ）に被るのを防ぐ。visibility:hidden で場所は保ったまま不可視にし、撮影後に
  // 元のインライン値へ厳密に戻す（元々 visibility を持っていたかを覚えておく）。撮影が
  // 重なっても最初の1回だけ隠し、最後の1つで戻す（captureStart/End の capDepth と対）。
  function hideEls() {
    if (!HIDE_SEL.length) return;
    hiddenEls = [];
    HIDE_SEL.forEach((sel) => {
      let list;
      try { list = document.querySelectorAll(sel); }
      catch (e) { return; }   // 不正なセレクタは黙って飛ばす（他の指定を巻き添えにしない）
      list.forEach((el) => {
        hiddenEls.push([el, el.style.visibility]);
        el.style.visibility = 'hidden';
      });
    });
  }
  function showEls() {
    hiddenEls.forEach((pair) => { pair[0].style.visibility = pair[1]; });
    hiddenEls = [];
  }

  // 撮影直前: バーを上へスライドさせて画面外へ退避する。退避し切ってから撮れるよう、
  // transition の完了（transitionend）で解決する Promise を返す（page.evaluate が待つ）。
  // 撮影が重なった場合は入れ子カウントで数え、最初の1回だけアニメーションする。
  function captureStart() {
    return new Promise((resolve) => {
      if (!els || !els.bar) { resolve(); return; }
      capDepth++;
      if (capDepth === 1) hideEls();   // 最初の撮影で hide_selectors を隠す（重なりは1回だけ）
      // 前回の「復帰待ち」が残っていれば取り消し、退避状態を維持する（撮影が重なっても
      // 途中でバーが降りてきて次のスクショに写り込まないように）。
      if (barTimer) { clearTimeout(barTimer); barTimer = null; }
      // 直前の撮影のシャッターフラッシュ（.frame.flash, CSS 500ms）が残っていると、
      // 次のスクショに赤みとして写り込む。復帰待ちを消すのと同時にフラッシュも畳む。
      if (frameTimer) { clearTimeout(frameTimer); frameTimer = null; }
      if (els.frame) els.frame.classList.remove('flash', 'fail');
      if (capDepth > 1) { resolve(); return; }   // 既に退避済み（別の撮影が進行中）
      const bar = els.bar;
      // バーが既に capturing（退避済み）なら classList.add は no-op で transitionend が
      // 飛ばず、CAP_FALLBACK_MS(500ms) まで無駄に待つ。退避済みなら即解決して待たない。
      if (bar.classList.contains('capturing')) { resolve(); return; }
      let done = false;
      const finish = () => {
        if (done) return;
        done = true;
        bar.removeEventListener('transitionend', finish);
        resolve();
      };
      bar.addEventListener('transitionend', finish);
      setTimeout(finish, CAP_FALLBACK_MS);   // transitionend が来ない場合の保険
      bar.classList.add('capturing');
    });
  }

  // 撮影直後: 進行中の撮影が無くなったら、まず全画面のシャッターフラッシュを出し
  //（シャッター確定の合図）、少し遅らせてからバーを元位置へスライドで戻す。フラッシュと
  // 復帰の動きを時間差にすることで、隠すときと同じ「上から降りてくる」動きが単独で見える。
  // 撮影が重なっていれば最後の1つで戻す。ok は _capture の done 有無で、成功は赤・失敗は
  // 琥珀にフラッシュ色を分ける（成否を渡さない無引数呼び出しは成功＝赤）。
  function captureEnd(ok) {
    if (!els || !els.bar) return;
    if (capDepth > 0) capDepth--;
    if (capDepth > 0) return;                     // まだ他の撮影が進行中
    showEls();                                    // 隠していた要素を元へ戻す（撮影は完了済み）
    // 1) シャッターフラッシュ（クラスを付け直して毎回アニメを頭から再生）。
    const failed = (ok === false);                // 明示的に false（保存全滅）のときだけ失敗色
    if (els.frame) {
      els.frame.classList.remove('flash', 'fail');
      void els.frame.offsetWidth;                 // リフローでアニメーションを確実に再スタート
      els.frame.classList.add('flash');
      if (failed) els.frame.classList.add('fail');
      if (frameTimer) clearTimeout(frameTimer);
      frameTimer = setTimeout(() => {
        if (els && els.frame) els.frame.classList.remove('flash', 'fail');
        frameTimer = null;
      }, FLASH_CLEAR_MS);
    }
    // 2) フラッシュの直後にバーを降ろす（動きが競合せず、戻りがはっきり見える）。
    if (barTimer) clearTimeout(barTimer);
    barTimer = setTimeout(() => {
      if (els && els.bar) els.bar.classList.remove('capturing');
      barTimer = null;
    }, BAR_RETURN_MS);
  }

  // バーが消えたら付け直すための監視。host は body の直接の子として append するので、
  // body の childList（直下の追加/削除）だけ見れば足りる。subtree は使わない（文書全体の
  // あらゆる変化で発火させない＝閲覧中の恒常負荷を避ける）。add_init_script 時点では body が
  // まだ無いことがあるため、build が body へ append できた後（＝body 確定後）に一度だけ張る。
  function ensureBarObserver() {
    if (barObserver || !document.body) return;
    barObserver = new MutationObserver(() => { if (!document.getElementById(ID)) build(); });
    barObserver.observe(document.body, { childList: true });
  }

  function build() {
    if (!document.body || document.getElementById(ID)) return;
    // 遷移直後に誤った状態（待機中）を一瞬見せないよう、先に現在の状態
    //（記録中/SPA検知/セレクタ）を Python へ問い合わせ、分かってから描画する。
    const finish = (state) => {
      if (!document.body || document.getElementById(ID)) return;
      host = document.createElement('div');
      host.id = ID;
      host.style.cssText = HOST_CSS;
      // closed にして、サイト側スクリプトから host.shadowRoot 経由で中へ入れないようにする。
      // open だと document.getElementById(ID).shadowRoot.querySelector(...).click() だけで
      // 記録の開始/停止・連写・セレクタ書き換えを起こせてしまい、token 照合が迂回される。
      // 内部からは以下の shadow 変数で操作できる（closed でも参照は返る）。
      shadow = host.attachShadow({ mode: 'closed' });
      shadow.innerHTML = TEMPLATE;

      const q = (name) => shadow.querySelector('[data-eac="' + name + '"]');
      els = {
        bar: q('bar'), dot: q('dot'), label: q('label'),
        toggle: q('toggle'), shot: q('shot'), open: q('open'), shots: q('shots'), peek: q('peek'),
        sel: q('selector'), selCount: q('sel-count'), history: q('history'),
        spaWrap: q('spa-wrap'), spaLabel: q('spa-label'), spa: q('spa'), spaText: q('spa-text'),
        frame: q('frame'),
      };

      // 静的な文言・ホバー説明を入れる。
      els.shot.textContent = L_SHOT;
      // 保存先フォルダを開くボタン。文言＋ホバー説明を入れる。
      els.open.textContent = L_OPEN;
      els.open.title = TITLE_OPEN;
      // アイコンボタンなので文言は入れず、ホバー説明（title）だけ付ける。
      // 可視テキストが無いのでアクセシブル名を aria-label で明示する。
      els.peek.title = TITLE_PEEK;
      els.peek.setAttribute('aria-label', ARIA_PEEK);
      // SPA検知はトグルスイッチ（role="switch"）。可視テキストは "ON"/"OFF" だけで
      // 何のスイッチか分からないため、横のラベルと同じ語をアクセシブル名として付ける。
      // 状態（checked）は apply() で aria-checked を随時反映する。
      els.spa.setAttribute('aria-label', L_SPA);
      els.sel.placeholder = PH_SEL;
      els.sel.title = TITLE_SEL;
      els.spaLabel.textContent = L_SPA;
      // 無効（セレクタ未設定）でも読めるよう、ラッパ／ラベル／ボタンに同じ説明を付ける。
      els.spaLabel.title = TITLE_SPA;
      els.spaWrap.title = TITLE_SPA;
      els.spa.title = TITLE_SPA;

      // 操作はすべて expose_binding 経由で Python へ通知する。第1引数に合言葉 TOK を付ける。
      // 呼び出しは callBinding に通す（退避済みの本物を使い、TOK をサイト側へ渡さない）。
      // 名前は Python から配られた C.bind を使う（この JS に名前のリテラルは置かない）。
      els.toggle.addEventListener('click', () => callBinding(C.bind.toggle, TOK));
      els.shot.addEventListener('click', () => callBinding(C.bind.shot, TOK));
      // 保存先フォルダを開く。Python 側が OS のファイルマネージャで開く（ローカル操作）。
      els.open.addEventListener('click', () => callBinding(C.bind.openFolder, TOK));
      // 透過トグルは見た目だけのローカル状態（Python への通知は不要）。押すたびに反転して再描画する。
      els.peek.addEventListener('click', () => { peekOn = !peekOn; apply(recording, spaOn); });
      els.spa.addEventListener('click', () => callBinding(C.bind.spaToggle, TOK));
      // 入力のたびにローカルで即座に見た目（SPAボタンの有効/無効・一致件数）を反映しつつ、
      // Python 側へも値を通知する（入力欄はフォーカス中なので apply が上書きしない）。
      els.sel.addEventListener('input', () => {
        apply(recording, spaOn, els.sel.value);
        callBinding(C.bind.setSelector, TOK, els.sel.value);
      });
      // 確定時（blur / Enter）に最終値をログへ（入力毎の氾濫を避ける）。
      els.sel.addEventListener('change', () => callBinding(C.bind.commitSelector, TOK, els.sel.value));

      document.body.appendChild(host);
      // バーが site の再描画で消えたら付け直すための監視を張る（body 確定後の今だけ）。
      ensureBarObserver();
      // 作り直したバーでは件数を必ず数え直させる（同じセレクタでも新しい要素は空のため）。
      countedSel = null;
      // 取得した現在の状態で最初から正しく描画する。
      apply(!!(state && state.recording), !!(state && state.spa), (state && state.selector) || '');
      // 撮影カウンタも現在値で描画する（再描画されたバーが 0 枚に戻って見えないように）。
      setShotCount((state && typeof state.count === 'number') ? state.count : shotCount);
      // セレクタ候補（datalist）も現在値で描画する（作り直したバーで候補が空にならないように）。
      setHistory((state && Array.isArray(state.history)) ? state.history : selHistory);
    };
    const fallback = { recording: recording, spa: spaOn, selector: selector };
    // 未注入・呼び出し不能なら callBinding が undefined を返すので、直前の状態で描画する。
    const pending = callBinding(C.bind.getState, TOK);
    if (pending && typeof pending.then === 'function') {
      pending.then(finish).catch(() => finish(fallback));
    } else {
      finish(fallback);
    }
  }

  // ---- Python(capture) から page.evaluate 経由で呼ぶページ側ヘルパ ----

  // ページ全文テキスト。innerText はシャドウ内の描画も合成し得るため、
  // 念のためホストを隠してから読み、元へ戻す。
  function bodyText() {
    if (!host) return document.body ? document.body.innerText : '';
    const prev = host.style.getPropertyValue('display');
    const prio = host.style.getPropertyPriority('display');
    host.style.setProperty('display', 'none', 'important');
    const t = document.body ? document.body.innerText : '';
    if (prev) host.style.setProperty('display', prev, prio); else host.style.removeProperty('display');
    return t;
  }

  // テキストを短いハッシュ（コンテンツ署名）にする。cyrb53 相当の簡易ハッシュで、衝突は
  // 実害小。長さ＋ハッシュを連結し、実質的に内容の異同を判別する。
  function hashText(text) {
    let h1 = 0xdeadbeef ^ text.length, h2 = 0x41c6ce57 ^ text.length;
    for (let i = 0; i < text.length; i++) {
      const ch = text.charCodeAt(i);
      h1 = Math.imul(h1 ^ ch, 2654435761);
      h2 = Math.imul(h2 ^ ch, 1597334677);
    }
    h1 = Math.imul(h1 ^ (h1 >>> 16), 2246822507) ^ Math.imul(h2 ^ (h2 >>> 13), 3266489909);
    h2 = Math.imul(h2 ^ (h2 >>> 16), 2246822507) ^ Math.imul(h1 ^ (h1 >>> 13), 3266489909);
    const hash = (h2 >>> 0).toString(16) + (h1 >>> 0).toString(16);
    return text.length + '_' + hash;
  }

  // SPA検知用のコンテンツ署名。セレクタ一致要素の innerText を連結して短いハッシュにする
  //（全文ではなくハッシュだけ返し、転送量を抑える）。バーはシャドウ内なので
  // querySelectorAll には紛れ込まず、隠す/戻す処理は不要。
  // セレクタ不正/該当なしは長さ 0 のハッシュ（＝「変化なし」とみなせる固定値）。
  function signature(sel) {
    let text = '';
    try {
      if (sel) {
        const parts = [];
        document.querySelectorAll(sel).forEach((el) => { parts.push(el.innerText || ''); });
        text = parts.join('\n');
      }
    } catch (e) { text = ''; }
    return hashText(text);
  }

  // SPA監視対象の署名。セレクタ指定時はその一致要素、未指定時はページ主要部
  //（main / article、無ければ本文全体）を対象にする。既定ルートを見ることで、セレクタ
  // 未設定でも URL が変わらない中身差し替え（SPA）を拾える。
  function spaSignature() {
    const sel = (selector || '').trim();
    if (sel) return signature(sel);
    const root = document.querySelector('main') || document.querySelector('article') || document.body;
    let text = '';
    try { text = root ? (root.innerText || '') : ''; } catch (e) { text = ''; }
    return hashText(text);
  }

  // SPA検知が実際に動く条件（記録ON かつ SPA検知ON）。監視の各所で参照する。
  function spaActive() { return spaOn && recording; }

  // 監視中(spaActive)へ切り替わった直後、またはセレクタが変わった直後は、現在の内容を
  // 「基準」に取り直す（開始/変更の直後に無駄撮りしないため）。Python 側で行っていた
  // reseed 相当をページ側で行う。apply から毎回呼ぶが、基準の再計算は遷移時だけ走る。
  //
  // SPA 監視の MutationObserver は、この spaActive の切り替わりに合わせて
  // observe / disconnect する。SPA検知を使っていない間（記録OFF or SPA検知OFF）は
  // Observer が動かないので、閲覧しているだけの利用者にコールバックのコストがかからない。
  function spaSyncBaseline() {
    const nowActive = spaActive();
    const sel = (selector || '').trim();
    const selChanged = sel !== spaPrevSelector;
    if (nowActive && (!spaPrevActive || selChanged)) {
      if (spaTimer) { clearTimeout(spaTimer); spaTimer = null; }
      spaNavPending = false;
      spaLastSig = spaSignature();
    }
    // 切り替わりの検知は spaPrevActive を更新する前に行う（下で更新）。
    if (nowActive && !spaPrevActive) spaObserverConnect();
    else if (!nowActive && spaPrevActive) spaObserverDisconnect();
    spaPrevActive = nowActive;
    spaPrevSelector = sel;
  }

  // SPA 監視 Observer の接続/切断。DOM 変化（childList / characterData）を捉えて
  // デバウンス確定する。属性変化は監視しない（クラス切替などの無関係な更新で
  // タイマーを張り直さないため）。Observer は初回接続時に一度だけ生成して使い回す。
  // 監視対象は documentElement（無ければ body、さらに document）へフォールバックする。
  function spaObserverConnect() {
    if (!spaObserver) spaObserver = new MutationObserver(spaSchedule);
    const root = document.documentElement || document.body || document;
    spaObserver.observe(root, { childList: true, subtree: true, characterData: true });
  }
  function spaObserverDisconnect() {
    if (spaObserver) spaObserver.disconnect();
  }

  // 変化を1件受けてデバウンスタイマーを張り直す。ただし連続変化が SPA_MAX_WAIT_MS を超えたら
  // 張り直さず、いま動いているタイマーで確定させる（動き続けるページで永遠に確定しないのを防ぐ）。
  function spaSchedule() {
    if (!spaActive()) return;
    const now = Date.now();
    if (spaTimer) {
      if (now - spaFirstAt >= SPA_MAX_WAIT_MS) return;   // 上限到達: 現タイマーで確定させる
      clearTimeout(spaTimer);
    } else {
      spaFirstAt = now;
    }
    spaTimer = setTimeout(spaFire, SPA_SETTLE_MS);
  }

  // デバウンス確定。落ち着いた時点の署名を求め、前回と違えば Python へ通知する。
  // 遷移直後（spaNavPending）は通知せず基準の取り直しだけ行う（URL変化側で1枚撮るため二重撮り回避）。
  function spaFire() {
    spaTimer = null;
    if (!spaActive()) return;
    const sig = spaSignature();
    if (spaNavPending) { spaNavPending = false; spaLastSig = sig; return; }
    if (sig !== spaLastSig) {
      spaLastSig = sig;
      callBinding(C.bind.spaChanged, TOK, sig);
    }
  }

  // ルート変化（SPA の画面遷移）。URL は変わるので Python 側の URL 監視が1枚撮る。ここでは
  // 通知せず基準を取り直すためにフラグを立て、遷移後の再描画を「変化」と誤検知して二重に
  // 撮らないようにする（遷移後の中身変化は次回以降で拾う）。
  function onRoute() {
    if (!spaActive()) return;
    spaNavPending = true;
    spaSchedule();
  }

  // --- ① Python から呼ぶページ側ヘルパを、ランダム名の隠しプロパティへ収める ---
  // 固定名（window.__eacApplyState 等）だと `'__eacApplyState' in window` で存在検知できてしまう。
  // 起動ごとのランダム名 NS の下へ 1 オブジェクトとしてまとめ、enumerable:false にして
  // Object.keys / for-in / JSON.stringify に出ないようにする。Python は NS を知っているので
  // window[NS].applyState(...) の形で呼べる（badge.py の *_call が NS 込みで式を組み立てる）。
  // NS 空（見た目だけ確認するテスト用ビルド）のときは公開しない。
  if (NS) {
    Object.defineProperty(window, NS, {
      value: {
        applyState: apply,
        setCount: setShotCount,
        setHistory: setHistory,
        captureStart: captureStart,
        captureEnd: captureEnd,
        bodyText: bodyText,
        signature: signature,
      },
      enumerable: false,
      configurable: true,
      writable: false,
    });
  }

  // スモークテスト専用の入り口。シャドウが closed になったことで host.shadowRoot から
  // 中を検査できなくなったため、テストだけが使えるアクセサを用意する。
  // 公開条件は「TOK が空」＝ build_badge_script() を token 無しで呼んだテスト用ビルドの
  // ときだけ。実運用は必ず token 付きで組み立てられる（badge.build_badge_script）ので、
  // この関数は本番のページには存在せず、closed の防御に穴を空けない。
  if (!TOK) window.__eac_debugRoot = () => shadow;

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', build);
  } else {
    build();
  }
  // **MutationObserver を documentElement に subtree で常時張らないこと** — 閲覧している
  // だけの利用者にも恒常的な負荷がかかる。必要な範囲でだけ張る:
  //   - バー再構築 → build 内 ensureBarObserver（body の childList のみ・body 確定後に張る）
  //   - SPA検知   → spaSyncBaseline 内 spaObserverConnect/Disconnect（監視中のときだけ接続）
  // SPA検知の署名は body 側の変化で決まるので、documentElement 常時監視は不要。
  //
  // ルート変化（SPA の画面遷移）のフック。pushState / replaceState を包み、popstate /
  // hashchange も拾う。いずれも onRoute（基準取り直し）へ回す。
  // **毎回無条件にラップしないこと** — (1) 元へ戻せない (2) 同一ドキュメントに複数回
  // 注入されると多重ラップになる。原参照を包み側に保持し、既にこのバーが包んだものは
  // 包み直さないガードを入れる（ラップは 1 回だけ）。
  const hookHistory = (name) => {
    const orig = history[name];
    if (typeof orig !== 'function' || orig.__eacOrig) return;   // 既に包み済みなら何もしない
    const wrapped = function () { const ret = orig.apply(this, arguments); onRoute(); return ret; };
    wrapped.__eacOrig = orig;   // 復元用に原参照を保持（history[name] = wrapped.__eacOrig で戻せる）
    history[name] = wrapped;
  };
  hookHistory('pushState');
  hookHistory('replaceState');
  window.addEventListener('popstate', onRoute);
  window.addEventListener('hashchange', onRoute);
  // 末尾はセミコロン無しの `}` で終える（badge.py が `(…)(<設定 JSON>);` で包んで呼び出す）。
}
