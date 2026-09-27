"""MCPは接続アダプター。意味モデルや業務ロジックはここに複製しない。"""
import json

from database import SessionLocal
from services import ontology, capa_service
from services.ontology_contract import definition


def _read(fn):
    with SessionLocal() as db:
        # 不正入力はFastMCPがisError=trueに変換。空の成功結果にしない。
        return fn(db)


def register(mcp):
    annotations = {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False}

    @mcp.resource("ontology://quality/definition", mime_type="application/json")
    def quality_definition() -> str:
        """製造品質の対象・関係・計算式・制約の定義。業務インスタンスは含まない。"""
        return json.dumps(definition(), ensure_ascii=False)

    @mcp.tool(annotations=annotations)
    def get_ontology_definition() -> dict:
        """Ontologyの対象型・関係名・計算式・CAPA操作制約を取得。意味を確認する際に使う。"""
        return definition()

    @mcp.tool(annotations=annotations)
    def resolve_ontology_entity(object_type: ontology.ObjectType, query: str, limit: int = 20) -> dict:
        """機械名(MachineLabel)・工程(Process)・顧客(Customer)を実データのIDに解決。
        報告書とCAPAはID完全一致。can_auto_select=falseなら候補を勝手に選ばず確認する。"""
        return _read(lambda db: ontology.resolve(db, object_type, query, limit))

    @mcp.tool(annotations=annotations)
    def get_ontology_object(object_type: ontology.ObjectType, object_id: str) -> dict:
        """型とIDで現在の対象・属性・出典を取得。架空のIDや別の型のIDはエラー。"""
        return _read(lambda db: ontology.get_object(db, object_type, object_id))

    @mcp.tool(annotations=annotations)
    def traverse_ontology_relation(object_type: ontology.ObjectType, object_id: str,
                                   relation: str, limit: int = 20, offset: int = 0) -> dict:
        """定義済み関係をDBの実キーでたどる。例: DefectReport.has_capa → CapaAction。
        機械/工程/顧客からreports、CAPAからfor_reportも可。next_offsetで続きが取れる。"""
        return _read(lambda db: ontology.traverse(db, object_type, object_id, relation, limit, offset))

    @mcp.tool(annotations=annotations)
    def query_quality_ontology(scope: ontology.QualityScope,
                               group_by: str = "MachineLabel", limit: int = 20, offset: int = 0) -> dict:
        """機械ID・工程ID・顧客ID・発生期間・報告状態・未クローズCAPA有無で照会。
        全該当報告の件数・記録上の不適合率・既知損失JPY・関連CAPA件数をサーバーで集計。
        objectsはページ内の根拠例。工場全体の不良率ではない。group_byはMachineLabel/Process/Customer。"""
        request = ontology.QualityQuery(scope=scope, group_by=group_by, limit=limit, offset=offset)
        return _read(lambda db: ontology.query_quality(db, request))

    @mcp.tool(annotations=annotations)
    def preview_capa_update(capa_id: str, status: str | None = None, effect_note: str | None = None,
                            owner: str | None = None, due_date: str | None = None) -> dict:
        """CAPAの変更前後・業務制約を検証。保存も承認もしない。valid=trueでも更新完了ではない。
        closedには空白以外の効果確認メモが必要。実行は明示依頼に基づきupdate_capa_action。"""
        patch = {k: v for k, v in {"status": status, "effect_note": effect_note,
                                  "owner": owner, "due_date": due_date}.items() if v is not None}
        return _read(lambda db: capa_service.preview_update(db, capa_id, patch))
