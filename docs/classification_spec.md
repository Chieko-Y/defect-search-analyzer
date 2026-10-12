# 苦情の分類ルール（v7）

## この文書について

この文書は、NHTSAに登録されたRAV4の苦情を、苦情本文に書かれている内容をもとに分類するためのルールをまとめたものです。
2022～2025年のRAV4の苦情を対象に、AI（Claude）を使って分類を行います。ただし、AIにすべてを任せるのではなく、どのような場合にどの分類を選ぶかを明確なルールとして定め、人が確認できる形にすることを目的としています。
読む人が、分類結果を見たときに「なぜこの分類になったのか」を確認でき、また分類に迷ったケースが出たときに、同じルールに戻って判断できることを想定しています。

## なぜ分類し直すのか

NHTSAには持ち主が選ぶカテゴリでの分類がありますが、今回の分析では、持ち主が選ぶカテゴリの分類ではなく、持ち主の実際の苦情文から車載テストの経験者からの視点で分類し直すことにしました。
例えば、雨のあとにエンストしたという同じような苦情でも、エンストと一緒に「Steering Power Low」という警告が出るため、持ち主によって ENGINE・STEERING・ELECTRICAL SYSTEM など選ぶカテゴリが異なり、複数のカテゴリに分かれていました。また、サンルーフの破裂に関する苦情を確認したところ、約6割が「その他」に分類されていました。「その他」が多いということは、既存の分類だけでは苦情の内容を十分に表せていない可能性があります。
さらに、RAV4の苦情で多く見られる画面や通信に関する問題を直接表すカテゴリがないことも分かりました。
そのため、苦情本文に書かれている実際の問題を分析しやすいように、ADAS、IVI/Display、Connectivity、Engine、Brakesなど、車両の機能を中心とした分類に作り直しました。
なお、分類するときAIには苦情本文だけを渡し、持ち主が選んだカテゴリは見せていません。見せるとAIがそのカテゴリに引っぱられてしまい、あとで「持ち主が選んだカテゴリ」と「苦情本文から付けた機能の分類」を比べる意味がなくなるためです。2つは別々に作られた分類として、答え合わせに使えるようにしています。

## 分類の考え方

分類するときに最も大切にしているのは、「書かれていること」と「推測」を分けることです。
苦情本文に書かれていないことは、基本的に推測せず Unknown とします。例えば、持ち主が「バッテリーが原因だと思う」と書いていても、ディーラーなどが原因を確認していなければ、それだけでバッテリーをroot causeとして分類しません。
一方で、VINから分かるパワートレインや、重複の判定など、データから確実に判断できるものはAIの推測に任せず、決められたデータやルールを使って判断します。
また、最初からすべてのケースを完璧にルール化するのではなく、実際の苦情を分類し、人の目で結果を確認しながら、分類しにくかったケースや「Other」に入ったケースを調べてルールを修正するという方法を取っています。
つまり、AIに判断を丸投げするのではなく、
「人がルールを作る → AIがそのルールで分類する → 人が結果を確認する → 必要に応じてルールを修正する」
という形で分類の精度を高めていきます。

---

## 項目と選択肢

苦情1件ごとに、次の項目を付ける。

| 項目 | 意味 | 選択肢 |
|---|---|---|
| root_function_group | 原因と考えられる機能（1つ） | ADAS / Brakes / Steering / Engine / Transmission/Drivetrain / Fuel System / Hybrid System / 12V Electrical/Battery / IVI/Display / Connectivity / Body/Glass / HVAC / Lighting / Airbags/Restraints / Tires/Wheels/Suspension / Other / Unknown |
| affected_function_groups | 苦情に出てくる機能すべて（root も含む） | 同上（複数） |
| symptom | 症状 | Unintended activation / Failure to operate / Intermittent operation / False warning / Display malfunction / Connection loss / Noise/Vibration / Performance degradation / Breakage / Fire/Smoke / Water leak / Other / Unknown |
| other_detail | symptom が Other のときの中身（英語で短く） | 自由記述。当てはまれば次から選ぶ：GPS location drift / Fuel fill shortage / Fuel leak/odor / Oil leak / Odor / Glass distortion / Surface deterioration / Alignment out of spec / Tire wear / Worn part / Park interlock / Battery drain / Design concern |
| trigger | 起きたときの車の状態 | Highway driving / City driving / Driving (road type unknown) / Low speed/Parking / Starting from stop / Stationary / Engine start / After specific operation / Always / Unknown |
| environment | 周りの条件 | Rain / Snow/Ice / Heat / Cold / None stated |
| safety_impact | 安全への影響 | 0 = 不便なだけ / 1 = 気が散る・軽い危険 / 2 = 制御を失う・衝突の危険 / 3 = 実際に衝突・けが・火災 |
| multiple_issues | 別々の問題が2つ以上書かれているか | true / false |
| aftermarket_involved | 後付け品が関係しているか | true / false |
| stated_cause | 苦情に書かれた原因・修理内容（英語で短く） | 自由記述（なければ空欄） |
| cause_source | stated_cause が誰の判断か | dealer / manufacturer / owner / none |
| evidence | root の根拠（苦情文から一番短い部分をそのまま写す） | 自由記述 |
| confidence | 書かれた内容から、どのくらいはっきり判断できたか | high / medium / low |
| unclear | 苦情文に書かれておらず Unknown にした項目の名前 | 項目名のリスト |

## AI に任せず、データで決めているもの

| 項目 | 決め方 |
|---|---|
| パワートレイン（ガソリン／ハイブリッド／PHEV） | VIN（先頭11文字）を NHTSA の vPIC API で解読する |
| 重複 | 同じ VIN ＋ 同じ事故日の苦情を重複とする |

---

## 判断のルール

### 全体
- 苦情文に書かれていることだけで判断する。書かれていないことは推測しない（Unknown）
- Other ＝「書かれているが選択肢にない」、Unknown ＝「書かれていない」

### root の選び方（2段階）

ステップ1：どの問題にするか（顧客が訴えている問題から選ぶ）
1. 「A が原因で B が起きた」と書かれていれば A（持ち主が「〇〇を替えたら直った」と結果まで書いていれば、それも含む）
2. 持ち主が一番訴えている問題が、苦情文の目印から分かれば、それ
   （目印：「My concern is 〜」とはっきり書いている／リコール・調査・修理を求めている／何度もディーラーに持ち込んでいる／「Aside from 〜」のように、ほかの問題をついでとして書いている）
3. 目印がなければ、安全への影響が一番大きいもの
4. それも同じなら、最初に書かれているもの

- 車が理由を表示して機能を止めた（雨・雪で「センサーがふさがれた」と出て運転支援が止まった など）のは正常な動作なので、問題に数えない（multiple_issues にも数えない）

ステップ2：その問題がどの機能のせいか
- ディーラー・修理工場・トヨタが、その問題の原因を特定または修理していれば、その機能
- なければ、症状が出ている機能
- 持ち主の推測（「バッテリーだと思う」）だけでは決めない
- 例外：原因が書かれておらず、複数の機能が一度におかしくなった → root は Unknown、multiple_issues は true

### 機能グループ
- 部品の種類ではなく、その部品が担う機能で分ける（前方カメラ → ADAS、車輪速センサー → Brakes、TPMS → Tires/Wheels/Suspension など）
- リアカメラ：画面は動くが映像だけ出ない → ADAS／画面ごと消える・固まる（ナビやラジオも使えない）→ IVI/Display
- 警告が出ただけの苦情は、警告の対象の機能で分ける。警告のせいでスピードなどが見えないことを訴えていれば IVI/Display
- 後付け品は、影響を受けた機能で分け、aftermarket_involved を true にする（ディーラーで付けたトヨタ純正品は false）

### symptom
- Breakage は、割れ・折れ・外れ・変形が目で見て分かると書かれているときだけ
- 部品が壊れて動かなくなった → Breakage（原因を優先）
- 見た目は壊れていないが動かない（ドアロックのアクチュエーターなど）→ Failure to operate
- 割れていない水漏れ → Water leak（ひびが見えて、そこから漏れるなら Breakage）
- 症状が順に進んだら、最初の症状（パワー低下 → エンスト なら Performance degradation）
- False warning は、警告がまちがいだったと分かるときだけ
- Other のときは、中身を other_detail に書く

### trigger
- 状況から車の状態がはっきり分かるときだけ推測してよい（赤信号で停車 → Stationary、駐車場から出る → Low speed/Parking）
- 「走行中」とだけ書かれていて道路の種類が分からない → Driving (road type unknown)
- City driving は街中、Highway driving は高速道路と書かれているときだけ
- 走っていたかどうかも分からない → Unknown
- Always は「いつも」「毎回」「ずっと」など、続いていることがはっきり書かれているときだけ

### safety_impact
- root の問題の、起こりうる危険で判断する（同じ苦情のほかの問題は含めない）
- 3 は、実際に衝突・けが・火災が起きたと苦情文に書かれているときだけ。NHTSA の入力欄（衝突・けが人の数）では決めない
- 体調不良（カビによるめまいなど）は「けが」に含めない
- 停車中か走行中かでは点数を変えない（分析のときに trigger と組み合わせて区別する）
- センター画面が消える・固まる・再起動する → 2（リアカメラの映像や警告が見えなくなるため）

### multiple_issues
- 同じ機能グループでも、別の部品が別々に壊れていれば true（エアバッグが開かず、シートベルトも効かなかった など）
- 同じ種類の部品に同じ故障が起きただけなら false（2つのドアのロック など）

### cause_source
- dealer ＝ ディーラー・修理工場の診断や修理、manufacturer ＝ トヨタの説明・リコール・サービスキャンペーン、owner ＝ 持ち主の考え、none ＝ 原因が書かれていない
- ディーラー・トヨタが調べて「異常なし」「仕様です」と言った → none（原因ではないため）

---

## 版の履歴

| 版 | 変えたこと |
|---|---|
| v1 | 最初の版 |
| v2 | environment・multiple_issues・aftermarket_involved を追加。パワートレインは VIN で判定 |
| v3 | 10件の人の目でのチェックを受けて、safety_impact・trigger・Breakage・機能の分け方のルールを追加 |
| v4 | stated_cause・cause_source を追加。原因不明で複数の機能がおかしくなったものは root を Unknown に。trigger に Driving (road type unknown) を追加 |
| v5 | root を「どの問題か」「どの機能のせいか」の2段階に。safety_impact は root の問題で付ける |
| v6 | root のステップ1で、持ち主が一番訴えている問題を優先（苦情文の目印で判断） |
| v7 | 全件の分類のあと Other の中身を数え、水漏れ（19件）を Water leak として選択肢に昇格 |

苦情を分類していく中で、新しいケースや分類しにくいケースが見つかるたびにルールを変更すると、以前の分類結果との整合性が取れなくなるためです。
そのため、ルールを変更するたびに版（v1、v2、…）として残し、「どの時点で、何を変更したのか」を記録するようにしています。
これにより、後から分類結果を見直したときに、その結果がどのバージョンのルールに基づいているのかを確認できます。
また、単に分類結果を良くするためだけに後からルールを変更するのではなく、実際の苦情を確認して、なぜ変更が必要になったのかを記録することで、分類ルールそのものの変化も追えるようにしています。
