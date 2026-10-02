# Cohort 快速上手與中文示範指南

這份指南對應 `feat/pnc-presentation-ready` 分支。`main` 尚未包含這個版本的完整介面，請先確認分支。介面目前使用英文，下面保留按鈕名稱，方便對照。

Cohort 可以查找佛典段落、比較用語，並讓 AI 提出有來源可查的解釋。研究者可以回頭看它搜尋了什麼、引用了哪一段，再決定是否接受。這次要展示的是這些操作怎麼幫助研究；譯者歸屬仍需要研究者判斷。

## 啟動

### 在目前這台機器開啟既有紀錄

在終端機執行：

```sh
cd /home/richard/github/cohort/.worktrees/presentation-ready
uv sync --extra dev --extra ui --extra evidence
```

這個工作目錄需要自己的 `.env`；其中 `OPENROUTER_MAX_OUTPUT_TOKENS` 請留白。若尚未設定，可從原工作目錄複製；以下指令不覆蓋既有檔案：

```sh
cp -n ../../.env .env
```

指定已經準備好的語料與段落向量，再啟動：

```sh
export LOCAL_CORPUS_ROOT=/home/richard/github/cohort/data/radich/corpus/T-stripped
export EVIDENCE_EMBEDDINGS_PATH=/home/richard/corpora/embeddings/mitra-qwen35-embedder.npz

uv run python scripts/serve_ui.py \
  --db /home/richard/github/cohort/data/pnc-30min/rehearsal.sqlite \
  --log /home/richard/github/cohort/data/pnc-30min/rehearsal.jsonl \
  --radich /home/richard/github/cohort/data/radich \
  --corpus --allow-writes --allow-runs --no-budget \
  --host 127.0.0.1 --port 18766
```

等終端機完成載入後，開啟 **http://127.0.0.1:18766/**。初次建立用語比較快取可能需要等一下。終端機要保持開著。

這會開啟先前儲存的研究紀錄。Graph 和 Findings 已有內容，是因為讀取同一份資料庫，沒有重新執行 AI。

`--allow-runs` 開啟 AI 執行功能；`--allow-writes` 允許研究者接受或拒絕提案。`--no-budget` 取消每次執行的金額停止門檻，API 費用仍會計算。查找原文、向量檢索和用語計算本身不會呼叫付費模型；Inquiry 和 Analyze this view 會。

### 如果從筆電連到伺服器

上面的啟動指令在伺服器執行。筆電另外開一個終端機，將 `USER` 和 `SERVER` 換成自己的帳號與主機：

```sh
ssh -N -L 18766:127.0.0.1:18766 USER@SERVER
```

接著在筆電瀏覽器開啟同一個網址。服務維持綁定 `127.0.0.1`，不直接公開語料。

### 在另一台機器安裝

需要 Git、uv、Python 3.11 以上，以及另外取得授權的 Radich 資料和段落向量檔。這些資料不在 Git 裡。若要重建介面，還需要 Node.js 與 npm。

```sh
git clone --branch feat/pnc-presentation-ready https://github.com/lopentu/cohort.git
cd cohort
uv sync --extra dev --extra ui --extra evidence
cp .env.example .env
```

編輯 `.env`，設定以下項目；路徑要換成新機器上的位置：

```dotenv
OPENROUTER_API_KEY=填入自己的金鑰
OPENROUTER_MODEL=填入要使用的模型識別碼
OPENROUTER_MODELS=填入可選模型識別碼，以逗號分隔
LOCAL_CORPUS_ROOT=/path/to/radich/corpus/T-stripped
EVIDENCE_EMBEDDINGS_PATH=/path/to/mitra-qwen35-embedder.npz
```

模型清單需包含不同模型家族，讓 worker 與 reviewer 分開。不要設定 `OPENROUTER_MAX_OUTPUT_TOKENS`。`.env` 不要提交到 Git。

若語料目錄缺少 `manifest.csv`，先建立來源清單：

```sh
uv run python scripts/radich_manifest.py /path/to/radich
```

若要帶既有研究到新機器，請在原服務停止寫入後，同時複製 `.sqlite` 和對應的 `.jsonl`。若要從空白開始，建立另一組檔案：

```sh
mkdir -p data/session
uv run python - <<'PY'
from cohort.graph import Graph

with Graph.open("data/session/research.sqlite", "data/session/research.jsonl"):
    pass
PY
```

接著使用上一節的 `serve_ui.py` 指令，把 `--db`、`--log` 和 `--radich` 換成新路徑即可。空白研究沒有 Graph 或 Findings，要等 Inquiry 提出並記錄內容後才會出現。

介面已隨這個分支附上。修改前端後才需要重建：

```sh
npm --prefix cohort/ui/frontend ci
npm --prefix cohort/ui/frontend run build
```

## 五個分頁各做什麼

| 分頁 | 可以做什麼 | 看結果時要注意什麼 |
|---|---|---|
| Corpus 語料 | 搜尋完全相同的詞句；並排閱讀兩筆結果；找內容相近的段落；標出相同字串；連到 CBETA | 精確搜尋依語料順序列出，沒有按相關性排名。Related passages 才有向量相似度排名。 |
| Vocabulary comparison 用語比較 | 選一篇文本，比較它的短字串使用頻率與各參考組的接近程度；排除其他文本後重算 | 比的是目標文本與各組的用語分布。最高分不能直接當成譯者歸屬。 |
| Inquiry 研究提問 | 記錄問題與研究指示，指定 worker 和 reviewer，執行搜尋與提案，回看執行紀錄 | worker 提出內容；reviewer 核對引用並提出審查意見；研究者決定是否接受。 |
| Graph 證據圖 | 檢查問題、文本、段落、主張、推測及其連結；查看來源核對與研究者決定 | 圖中的內容限於已記錄的資料。Show exploration 可以補看搜尋活動。 |
| Findings 研究發現 | 把主張與推測整理成可閱讀的條目，查看引用、其他解釋及審查結果 | 條目可能尚未通過核對或尚未被接受，出現在這裡不等於成立。 |

常見操作順序是 **Corpus 找段落 → Inquiry 調查 → Graph 查來源 → Findings 讀結果**。用語比較可以先幫你找出值得追問的現象，再把問題交給 Inquiry。單純搜尋或計算不會自動把所有結果加入 Graph。

Graph 和用語比較都有 **Analyze this view**。可以請 AI 解釋目前畫面，接著追問，也可以讓它用唯讀工具補查資料。這段對話不會自動變成 Graph 裡的研究提案；要留下正式提案，請使用 Inquiry。

## 幾個容易看錯的地方

### 向量相似度與相同字串

Related passages 使用預先算好的段落向量，以 cosine similarity 排名。目前檔名顯示的嵌入模型是 `mitra-qwen35-embedder`；介面也會標示模型資訊。這項檢索不會即時產生新向量，涵蓋範圍限於已建立索引的本地語料。

分數高表示向量接近，仍要讀內容確認。共同主題、常見表述都可能讓分數偏高。分數不是「兩段有關係的機率」，也不能用來推定同一位譯者。

**Shared wording** 另外比對畫面上選定的兩個段落，把連續相同的中文字串標在原文內。介面標出四字以上的連續字串；它沒有比較兩部經的全文。最長相同字串的長度，也不等於全部重複文字的總量。這裡的來源位置是本地文本的字元位置，不能直接當成 CBETA 行號。

### 用語比較中的組別、詞表與顏色

參考組沿用 Radich 的目錄分類，包含譯者組及混合組。Cohort 沒有依用語重新分群。`pre-Dhr-other` 指「竺法護之前的其他材料」，是混合組；`grey` 指譯者不確定的材料，不是譯者組，也不納入參考組的用語分布；它只提供 Frequent corpus strings 的選詞材料。

選定的詞表決定要計算哪些短字串：

- **Radich's list for the Dharmarakṣa dictionary**：Radich 為竺法護辭典工作整理的字串。列在表上不表示只有竺法護使用，也不保證能區分所有譯者。
- **Frequent corpus strings**：從譯者不確定的材料中，按頻率選出的字串。這是另一種選詞方式；常見字串不一定有區分力。
- **Combined**：合併兩份詞表。

程式會計算目標文本及參考組中這些字串的相對頻率，再比較用語分布。目標所屬的整部作品會從參考資料中排除，避免拿自己和自己比。

原文的 A、B 顏色表示：這個字串在 A 組或 B 組的相對頻率較高。不能因此把某段文字分配給 A 或 B 譯者。沒有上色的文字，也不表示沒有相同用語；它可能不在選定詞表內。

### Graph 的主張、推測與狀態

**Claim（主張）** 是提案中的一個可核查陳述，例如某段出現特定字句；**Conjecture（推測）** 是要進一步檢驗的解釋，例如重複用語可能來自引用。這不是單靠句型就能機械判定的分類。推測需要附上可反駁它的查詢或檢驗方式；查詢得到結果後仍需解讀。

| 狀態 | 意義 |
|---|---|
| Proposed 已提出 | 已記錄提案，尚未通過升級所需的核對。可能沒有審查，也可能引用失敗或 reviewer 有異議；不代表還在執行。 |
| Attested 已核對 | 所需的引用與程序檢查已通過。這不保證歷史解釋正確。 |
| Accepted 已接受 | 研究者接受這個已核對的提案，允許它作為研究紀錄中的可引用內容。 |
| Rejected 已拒絕 | 研究者拒絕提案；拒絕與理由仍保留在紀錄中。 |

點選節點可以看提案者、模型、理由、來源與審查結果。Claim 和 Conjecture 都由 worker 提出，reviewer 不會替研究者接受。搜尋查詢是操作紀錄，不需要一律先接到文本、再接到段落；圖也不是「每個推測都必須由固定數量的主張組成」。

## 三十分鐘怎麼安排

建議先用約十八分鐘介紹，再用十分鐘操作，最後兩分鐘回到限制與致謝。投影片不用逐字念，也不用等現場 AI 跑完。

現在的可編輯版本是 [cohort-pnc-2026-main.pptx](presentation/cohort-pnc-2026-main.pptx)。請以這份為準；舊版 PowerPoint 與 PDF 不一定包含後來修改。

開場可以這樣說：

> 我們想看看，AI 能不能幫研究者找材料、比較段落，再把它提出的解釋連回原文。今天用佛典做例子。不同時期的譯本和註解，可能保留相近的內容，但文字不一定相同；反過來，文字很像，也可能只是引用或常見套語。

接著致謝：

> 感謝 Michael Radich 提供研究資料，包括他整理、修改自 CBETA 的語料、目錄分類，以及為竺法護辭典工作準備的字串表。我們借用這些材料測試工具，今天展示的結果不構成新的譯者判定。

### 操作一 找到候選段落，再讀原文

若要先展示精確搜尋，在 **Corpus → Exact phrase** 輸入「如是我聞」，在兩筆結果上按 **Compare**，就能並排閱讀。這是常見開頭，適合解釋搜尋與比對操作；不能拿這句相同就推定兩篇有直接關係。結果若達上限，畫面只列出部分命中，並非最相關的前幾筆。接著切到 Related passages 做下面的比較。

1. 開 **Corpus → Related passages**，按 **Lotus Sūtra · Dharmarakṣa**。
2. 說明選定的是竺法護的《正法華經》（T0263）。這個按鈕使用目錄中的 `T0263-rest` 單位，從來源位置 4000 開始，避開開頭。
3. 查看結果的經名與內容。若有鳩摩羅什《妙法蓮華經》（T0262）的段落，選它並排閱讀。`T0262-exDevadatta` 是不含另列提婆達多品的目錄單位。
4. 按 **Shared wording**，看原文中的相同字串。請照畫面描述，不要預先說「只有幾個字相同」；換段落位置會改變結果。
5. 指出 **Investigate this pair**。按下會帶著兩段來源開啟 Inquiry 草稿，可以先展示草稿，不必立刻執行。

可以這樣講：

> 這是同一部經的不同時期譯本，所以有理由拿來比較。向量搜尋先找候選段落，我們再讀內容、查相同字串。它排得高，只表示值得看，還不能說兩段已經確定對應。

若首筆是別部經，不必迴避：讀經名與段落，說明它可能因共同內容或表述而接近。T 編號是目錄識別碼，不能拿編號相近當作語意相近的證據。

### 操作二 看參考材料會不會改變用語比較

1. 開 **Vocabulary comparison**，選 **T0603《陰持入經》**。這部經傳統上與安世高相關；它是我們觀察工具行為的例子。
2. 選 **Radich's list for the Dharmarakṣa dictionary**，看完整排名、組名與原文上色。先解釋它比的是短字串的使用頻率。
3. 記下畫面上的最高組別與分數。展開排除設定，按 **Exclude T1694 commentary**。
4. T1694 是《陰持入經註》。重算後比較排名與分差，只報畫面實際算出的數字。目標文本、詞表與其他設定要保持相同。
5. 說明這次只從參考組移除註解，沒有從 T0603 刪除段落。若更換詞表，前後兩次也必須用同一份詞表。

可以這樣講：

> 這部註解放在「竺法護之前的其他材料」這一組。它保留了經文的用語，所以可能把整組的用語分布拉近。現在把註解移出參考資料，再看排名。若結果改變，我們就知道原來的比較受到這份材料影響，接下來要讀重複的段落，判斷是不是引用造成的。

這個例子能說明跨時期的經文與註解如何影響比較。不能只因為排除後安世高組上升，就宣布工具找到了譯者。

### 操作三 從調查紀錄回到來源

事先完成一筆 Inquiry，現場用同一筆問題展示 **Inquiry → Graph → Findings**。可以用以下中文草稿；介面允許中文輸入。

**Research question（研究問題）**

> 《陰持入經》（T0603）和《陰持入經註》（T1694）有哪些重複用語？這些重複用語會怎麼影響《陰持入經》與其他文本的用語比較？

**Research instructions（研究指示）**

> 查閱兩部文本，選出可回到原文核查的重複段落，列出來源識別碼與位置。區分常見套語和較具體的重複內容。固定目標與詞表，比較排除 T1694 前後的結果，並說明還有哪些可能的解釋。不要判定譯者，也不要把相同字串直接說成已證實的引用關係。證據不足時說明缺什麼。

研究問題是想知道什麼；研究指示是希望 AI 怎麼查、報告哪些材料。原本的 Answer criteria 儲存欄位沿用在研究指示中，並不會自動替答案打分數。

1. 在 **Inquiry** 選已完成的紀錄，展開一兩項工具操作，說明 worker 查了什麼、為什麼查。
2. 切到 **Graph**，只勾選這一筆研究問題。點一個主張或推測，再點它引用的段落，查看原文位置與核對結果。
3. 開 **Show exploration**，展示搜尋範圍可以比正式提案引用的材料更廣。看完可關閉，避免畫面太密。
4. 切到 **Findings**，讀同一筆提案的說明與其他可能解釋。說明研究者可以接受或拒絕；不要為了展示按鈕就接受自己尚未確認的內容。

可以這樣講：

> AI 提出的解釋可以成為下一步調查的起點。我想追問它時，可以看到它查過哪些資料，以及哪一段原文支持這個說法。另一個模型核對引用，但內容的解讀還是要由研究者確認。

切換分頁不會停止 Inquiry。結果與執行紀錄會儲存，之後用同一組資料庫和事件紀錄啟動，就能繼續查看；關掉伺服器會中斷尚未完成的執行，不能期待重啟後自動續跑。

## 目前的限制與現場備案

- **用語比較尚不能可靠地辨認譯者。** 詞表偏重某項辭典工作，常見套語與篇幅也會影響結果。可以用它找值得閱讀、排除或追問的材料，不能把排名當成歸屬證明。
- **引用核對不等於解釋正確。** reviewer 可能失敗或提出異議；原文真的有這句話，也不表示它支持 AI 的全部推論。
- **來源與索引有範圍限制。** 目前用的是選定本地語料，並非 CBETA 全庫；目錄單位也可能是章、殘餘部分或合併單位。報告涵蓋範圍時以畫面清單為準。
- **相同字串比對還不是校勘。** 它沒有自動處理異體字、所有異文或整部作品的對應關係。
- **跨時期比較需要歷史知識。** Cohort 可以比較不同時期的譯本與註解，但不會因此自動推定年代、借用方向或傳承系譜。
- **關係類型能顯示，不代表目前會自動建立。** Graph 可記錄 quotation、parallel、descent 等類型；目前使用的 Radich 純文字來源沒有原始 CBETA XML 的關係標記，worker 也沒有建立 quotation 或 descent 關係的工具。不要承諾現場會自動產生這些連結。
- **執行可能沒有完整答案。** worker 有回合上限；找不到材料、審查有異議或執行失敗都應照實呈現。現場先用完成的紀錄，避免等待 API。

上台前確認：能開啟網址、五個分頁都在、法華經快捷搜尋能回傳、T0603 能重算、準備好的 Inquiry 紀錄仍在。Graph 若顯示截斷提示，先只選一筆研究問題，不要把當下畫面當成整張圖。

若沒有 Related passages，先檢查 `EVIDENCE_EMBEDDINGS_PATH`；若沒有用語比較，檢查 `--radich` 和 `evidence` 套件；若 Inquiry 不能開始，檢查金鑰、語料及 `--allow-runs`。如果頁面顯示舊介面，確認啟動目錄與分支，再重建前端並重新整理。

語料、向量檔、`.env` 和研究資料庫都不隨程式碼推送。要帶到另一台機器，另外準備有授權的資料；停止服務時按 `Ctrl+C`，保留 `.sqlite` 與 `.jsonl`，下次才能開啟同一份研究。
