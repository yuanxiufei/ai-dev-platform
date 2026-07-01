"""
Cypher 风格图查询引擎 — openCypher 只读子集。

    MATCH (n:NodeType)-[r:EdgeType]->(m:NodeType)
    WHERE n.property = 'value'
    RETURN n.name, m.qualified_name
    ORDER BY n.name ASC
    LIMIT 10
"""

from __future__ import annotations
import re
import sqlite3
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Optional


# ═══ Token / Lexer ═══

class TokenType(Enum):
    KEYWORD=auto(); IDENTIFIER=auto(); STRING=auto(); NUMBER=auto()
    LPAREN=auto(); RPAREN=auto(); LBRACKET=auto(); RBRACKET=auto()
    COLON=auto(); DOT=auto(); COMMA=auto(); ARROW_R=auto(); ARROW_L=auto()
    EQUALS=auto(); STAR=auto(); PIPE=auto(); EOF=auto()

KW = {
    "MATCH","WHERE","RETURN","ORDER","BY","ASC","DESC","LIMIT",
    "CONTAINS","IN","AND","OR","NOT","COUNT","AS","DISTINCT",
    "IS","NULL","TRUE","FALSE",
}

@dataclass
class Token:
    type: TokenType; value: str; pos: int = 0

class Lexer:
    def __init__(self, s: str): self._s=s; self._p=0; self._ts: list[Token]=[]
    def tokenize(self) -> list[Token]:
        self._ts=[]; self._p=0
        while self._p < len(self._s):
            ch = self._s[self._p]
            if ch.isspace(): self._p+=1; continue
            if ch=='(': self._emit(TokenType.LPAREN,'('); self._p+=1
            elif ch==')': self._emit(TokenType.RPAREN,')'); self._p+=1
            elif ch=='[': self._emit(TokenType.LBRACKET,'['); self._p+=1
            elif ch==']': self._emit(TokenType.RBRACKET,']'); self._p+=1
            elif ch==':': self._emit(TokenType.COLON,':'); self._p+=1
            elif ch=='.': self._emit(TokenType.DOT,'.'); self._p+=1
            elif ch==',': self._emit(TokenType.COMMA,','); self._p+=1
            elif ch=='*': self._emit(TokenType.STAR,'*'); self._p+=1
            elif ch=='=': self._emit(TokenType.EQUALS,'='); self._p+=1
            elif ch=='|':
                if self._p+1<len(self._s) and self._s[self._p+1]=='|': self._p+=2; continue
                self._emit(TokenType.PIPE,'|'); self._p+=1
            elif ch=='-':
                if self._p+1<len(self._s) and self._s[self._p+1]=='>': self._emit(TokenType.ARROW_R,'->'); self._p+=2
                else: self._p+=1
            elif ch=='<':
                if self._p+1<len(self._s) and self._s[self._p+1]=='-': self._emit(TokenType.ARROW_L,'<-'); self._p+=2
                else: self._p+=1
            elif ch in "'\"": self._tok_str(ch)
            elif ch.isdigit() or (ch=='-' and self._p+1<len(self._s) and self._s[self._p+1].isdigit()): self._tok_num()
            elif ch.isalpha() or ch=='_' or ch=='`': self._tok_ident()
            else: self._p+=1
        self._emit(TokenType.EOF,'')
        return self._ts
    def _tok_str(self, q):
        self._p+=1; v=''
        while self._p<len(self._s):
            c=self._s[self._p]
            if c=='\\': self._p+=1; v+=self._s[self._p] if self._p<len(self._s) else '\\'
            elif c==q: self._emit(TokenType.STRING,v); self._p+=1; return
            else: v+=c
            self._p+=1
    def _tok_num(self):
        v=''
        if self._s[self._p]=='-': v='-'; self._p+=1
        while self._p<len(self._s) and (self._s[self._p].isdigit() or self._s[self._p]=='.'): v+=self._s[self._p]; self._p+=1
        self._emit(TokenType.NUMBER,v)
    def _tok_ident(self):
        v=''
        if self._s[self._p]=='`':
            self._p+=1
            while self._p<len(self._s) and self._s[self._p]!='`': v+=self._s[self._p]; self._p+=1
            if self._p<len(self._s): self._p+=1
        else:
            while self._p<len(self._s) and (self._s[self._p].isalnum() or self._s[self._p]=='_'): v+=self._s[self._p]; self._p+=1
        self._emit(TokenType.KEYWORD if v.upper() in KW else TokenType.IDENTIFIER, v.upper() if v.upper() in KW else v)
    def _emit(self, t, v): self._ts.append(Token(t, v, self._p))


# ═══ AST ═══

@dataclass
class NodePat: var: str=""; labels: list[str]=field(default_factory=list)

@dataclass
class RelPat: var: str=""; types: list[str]=field(default_factory=list); dir: str="right"

@dataclass
class WhereCond: col: str=""; op: str="="; val: Any=None

@dataclass
class RetItem: expr: str=""; alias: str=""

@dataclass
class OrdItem: expr: str=""; dir: str="ASC"

@dataclass
class MatchClause:
    pats: list[tuple[NodePat, Optional[RelPat], Optional[NodePat]]] = field(default_factory=list)

@dataclass
class CypherAST:
    match: Optional[MatchClause]=None
    where_conds: list[WhereCond]=field(default_factory=list)
    ret: list[RetItem]=field(default_factory=list)
    order: list[OrdItem]=field(default_factory=list)
    limit: Optional[int]=None
    distinct: bool=False


# ═══ Parser ═══

class Parser:
    def __init__(self, ts): self._ts=ts; self._i=0
    def parse(self) -> CypherAST:
        ast=CypherAST()
        while not self._eof():
            kw=self._peek()
            if kw and kw.type==TokenType.KEYWORD:
                v=kw.value
                if v=="MATCH": ast.match=self._parse_match()
                elif v=="WHERE": ast.where_conds=self._parse_where()
                elif v=="RETURN": ast.ret,ast.distinct=self._parse_return()
                elif v=="ORDER": ast.order=self._parse_order()
                elif v=="LIMIT": ast.limit=self._parse_limit()
                else: self._adv()
            else: self._adv()
        return ast

    def _parse_match(self) -> MatchClause:
        self._expkw("MATCH"); m=MatchClause()
        while True:
            l=self._parse_node()
            t=self._peek()
            if t and t.type in (TokenType.KEYWORD,TokenType.EOF) and (t.type==TokenType.EOF or t.value in ("WHERE","RETURN","MATCH","ORDER","LIMIT")):
                m.pats.append((l,None,None)); break
            if t and t.type==TokenType.COMMA: m.pats.append((l,None,None)); self._adv(); continue
            r=self._parse_rel()
            t=self._peek()
            ri=None
            if t and t.type==TokenType.LPAREN: ri=self._parse_node()
            m.pats.append((l,r,ri))
            t=self._peek()
            if t and t.type==TokenType.COMMA: self._adv(); continue
            break
        return m

    def _parse_node(self) -> NodePat:
        self._exp(TokenType.LPAREN); n=NodePat()
        t=self._peek()
        if t and t.type==TokenType.IDENTIFIER: n.var=self._adv().value
        t=self._peek()
        if t and t.type==TokenType.COLON:
            self._adv()
            while self._peek() and self._peek().type==TokenType.IDENTIFIER:
                n.labels.append(self._adv().value)
                if self._peek() and self._peek().type==TokenType.COLON: self._adv(); continue
                break
        self._exp(TokenType.RPAREN)
        return n

    def _parse_rel(self) -> RelPat:
        r=RelPat(); t=self._peek()
        if t and t.type==TokenType.ARROW_L: r.dir="left"; self._adv()
        if self._peek() and self._peek().type==TokenType.LBRACKET:
            self._adv(); self._parse_rel_d(r); self._exp(TokenType.RBRACKET)
        if self._peek() and self._peek().type==TokenType.ARROW_R: self._adv()
        return r

    def _parse_rel_d(self, r):
        t=self._peek()
        if t and t.type==TokenType.IDENTIFIER:
            nxt=self._peek(1)
            if nxt and nxt.type==TokenType.COLON: r.var=self._adv().value; self._adv()
            else: r.var=self._adv().value; return
        elif t and t.type==TokenType.COLON: self._adv()
        else: return
        if not self._peek(): return
        while self._peek() and self._peek().type==TokenType.IDENTIFIER:
            r.types.append(self._adv().value)
            if self._peek() and self._peek().type==TokenType.COLON: self._adv(); continue
            break

    def _parse_where(self) -> list[WhereCond]:
        self._expkw("WHERE"); conds=[]
        while True:
            c=self._parse_one_cond()
            if c: conds.append(c)
            else: break
            t=self._peek()
            if t and t.type==TokenType.KEYWORD and t.value in ("AND","OR"): self._adv(); continue
            break
        return conds

    def _parse_one_cond(self) -> Optional[WhereCond]:
        t=self._peek()
        if not t or t.type==TokenType.EOF: return None
        neg=False
        if t.type==TokenType.KEYWORD and t.value=="NOT": neg=True; self._adv(); t=self._peek()
        if not t or t.type!=TokenType.IDENTIFIER: return None
        c=WhereCond(col=self._adv().value)
        if self._peek() and self._peek().type==TokenType.DOT: self._adv(); c.col+="."+self._adv().value
        t=self._peek()
        if not t: return None
        if t.type==TokenType.EQUALS: c.op="!=" if neg else "="; self._adv(); c.val=self._parse_val()
        elif t.type==TokenType.KEYWORD:
            if t.value=="CONTAINS": c.op="CONTAINS"; self._adv(); c.val=self._parse_val()
            elif t.value=="IN": c.op="NOT IN" if neg else "IN"; self._adv(); c.val=self._parse_list()
            elif t.value=="IS":
                self._adv(); nxt=self._peek()
                if nxt and nxt.type==TokenType.KEYWORD and nxt.value=="NULL": c.op="IS NULL"; self._adv()
                elif nxt and nxt.type==TokenType.KEYWORD and nxt.value=="NOT":
                    self._adv()
                    if self._peek() and self._peek().type==TokenType.KEYWORD and self._peek().value=="NULL": c.op="IS NOT NULL"; self._adv()
        elif t.value in (">","<"): c.op=t.value; self._adv()
            if self._peek() and self._peek().value=="=": c.op+="="; self._adv()
            c.val=self._parse_val()
        return c if c.op else None

    def _parse_val(self):
        t=self._peek()
        if not t: return None
        if t.type==TokenType.STRING: return self._adv().value
        if t.type==TokenType.NUMBER: v=self._adv().value; return int(v) if v.lstrip('-').isdigit() else float(v)
        if t.type==TokenType.KEYWORD:
            if t.value=="TRUE": self._adv(); return True
            if t.value=="FALSE": self._adv(); return False
            if t.value=="NULL": self._adv(); return None
        if t.type==TokenType.IDENTIFIER: return self._adv().value
        return None

    def _parse_list(self):
        self._exp(TokenType.LBRACKET); vs=[]
        while self._peek() and self._peek().type!=TokenType.RBRACKET:
            v=self._parse_val()
            if v is not None: vs.append(v)
            if self._peek() and self._peek().type==TokenType.COMMA: self._adv()
        self._exp(TokenType.RBRACKET)
        return vs

    def _parse_return(self) -> tuple[list[RetItem],bool]:
        self._expkw("RETURN"); dist=False
        if self._peek() and self._peek().type==TokenType.KEYWORD and self._peek().value=="DISTINCT": dist=True; self._adv()
        items=[]
        while True:
            t=self._peek()
            if not t or t.type==TokenType.EOF: break
            if t.type==TokenType.KEYWORD and t.value in ("ORDER","LIMIT","MATCH","WHERE"): break
            it=RetItem()
            if t.type==TokenType.STAR: it.expr="*"; self._adv()
            elif t.type==TokenType.KEYWORD and t.value=="COUNT":
                self._adv(); self._exp(TokenType.LPAREN)
                inner="*" if (self._peek() and self._peek().type==TokenType.STAR) else self._adv().value
                if self._peek() and self._peek().type==TokenType.DOT: self._adv(); inner+="."+self._adv().value
                self._exp(TokenType.RPAREN); it.expr=f"count({inner})"
            else: it.expr=self._parse_retexpr()
            t=self._peek()
            if t and t.type==TokenType.KEYWORD and t.value=="AS": self._adv(); it.alias=self._adv().value
            if it.expr: items.append(it)
            if self._peek() and self._peek().type==TokenType.COMMA: self._adv(); continue
            break
        return items, dist

    def _parse_retexpr(self):
        v=self._adv().value
        if self._peek() and self._peek().type==TokenType.DOT: self._adv(); v+="."+self._adv().value
        return v

    def _parse_order(self):
        self._expkw("ORDER"); self._expkw("BY"); items=[]
        while True:
            t=self._peek()
            if not t or t.type!=TokenType.IDENTIFIER: break
            e=self._adv().value
            if self._peek() and self._peek().type==TokenType.DOT: self._adv(); e+="."+self._adv().value
            d="ASC"
            if self._peek() and self._peek().type==TokenType.KEYWORD and self._peek().value in ("ASC","DESC"): d=self._adv().value
            items.append(OrdItem(e,d))
            if self._peek() and self._peek().type==TokenType.COMMA: self._adv(); continue
            break
        return items

    def _parse_limit(self):
        self._expkw("LIMIT")
        return int(self._adv().value)

    def _peek(self,off=0): return self._ts[self._i+off] if self._i+off<len(self._ts) else None
    def _adv(self): self._i+=1; return self._ts[self._i-1]
    def _eof(self): return self._i>=len(self._ts) or self._ts[self._i].type==TokenType.EOF
    def _exp(self, t):
        tk=self._adv()
        if tk.type!=t: raise SyntaxError(f"Expected {t}, got {tk.type}({tk.value})")
        return tk
    def _expkw(self, kw):
        tk=self._adv()
        if tk.type!=TokenType.KEYWORD or tk.value!=kw: raise SyntaxError(f"Expected {kw}, got {tk.value}")
        return tk


# ═══ Query Engine: AST → SQLite / 内存执行 ═══

NODE_COLS = {
    "id":"id","name":"name","file_path":"file_path","line_start":"line_start",
    "line_end":"line_end","qualified_name":"qualified_name","signature":"signature",
    "language":"language","node_type":"node_type","type":"node_type",
}
EDGE_COLS = {"source_id":"source_id","target_id":"target_id","edge_type":"edge_type","type":"edge_type"}


class QueryEngine:
    """Cypher AST → SQL → SQLite；回退到 CodeGraph 内存执行"""

    def __init__(self, db_path: str = "", graph: Any = None):
        self._db = db_path
        self._gr = graph

    def execute(self, query: str) -> dict:
        try:
            ast = Parser(Lexer(query).tokenize()).parse()
            if not ast.match: return {"error":"MATCH clause required","results":[]}
            if self._db: return self._run_sql(ast)
            return self._run_mem(ast)
        except Exception as e:
            return {"error": str(e), "results": []}

    # ── SQLite 执行 ──

    def _run_sql(self, ast: CypherAST) -> dict:
        db = sqlite3.connect(self._db); db.row_factory = sqlite3.Row
        try:
            sql, params = self._build_sql(ast)
            rows = db.execute(sql, params).fetchall()
            results = [dict(r) for r in rows]
            is_count = ast.ret and ast.ret[0].expr.startswith("count(")
            total = results[0].get("count(*)", len(results)) if is_count and results else len(results)
            return {"results": results, "total": total, "has_more": ast.limit is not None and len(results) >= (ast.limit or 0)}
        finally:
            db.close()

    def _build_sql(self, ast: CypherAST) -> tuple[str, list]:
        from_clauses=[]; join_conds=[]; where_parts=[]; params=[]
        var_map={}; has_nodes=False; has_edges=False

        for lp, rp, rp2 in ast.match.pats:
            # 左节点
            if lp.var:
                al=lp.var; var_map[lp.var]=(al,"node"); has_nodes=True
                from_clauses.append(f"graph_nodes AS {al}")
                if lp.labels:
                    where_parts.append("("+" OR ".join([f"{al}.node_type=?"]*len(lp.labels))+")")
                    params.extend(lp.labels)
            # 右节点
            if rp2 and rp2.var:
                al=rp2.var
                if al not in [v[0] for v in var_map.values() if v[1]=="node"]:
                    var_map[rp2.var]=(al,"node"); has_nodes=True
                    from_clauses.append(f"graph_nodes AS {al}")
                    if rp2.labels:
                        where_parts.append("("+" OR ".join([f"{al}.node_type=?"]*len(rp2.labels))+")")
                        params.extend(rp2.labels)
            # 关系
            if rp:
                ral=rp.var or f"rel_{len(from_clauses)}"
                var_map[ral]=(ral,"edge"); has_edges=True
                from_clauses.append(f"graph_edges AS {ral}")
                if rp.types:
                    where_parts.append("("+" OR ".join([f"{ral}.edge_type=?"]*len(rp.types))+")")
                    params.extend(rp.types)
                if lp.var:
                    join_conds.append(f"{lp.var}.id = {ral}.source_id")
                    if rp2 and rp2.var: join_conds.append(f"{rp2.var}.id = {ral}.target_id")

        # SELECT
        sel=[]
        if not ast.ret:
            sel=["*"]
        for it in ast.ret:
            if it.expr=="*":
                sel.append("*")
            elif it.expr.startswith("count("):
                sel.append(it.expr)
            else:
                col=self._resolve_col(it.expr, var_map)
                sel.append(f"{col} AS {it.alias}" if it.alias else col)
        sel_str=", ".join(sel) if sel else "*"

        # FROM
        tables=list(dict.fromkeys(from_clauses))
        if not tables: tables=["graph_nodes AS n"]
        from_str=", ".join(tables)

        # WHERE
        for c in ast.where_conds:
            col=self._resolve_col(c.col, var_map)
            if not col: continue
            if c.op=="CONTAINS":
                where_parts.append(f"{col} LIKE ?"); params.append(f"%{c.val}%")
            elif c.op in ("=","!=",">","<",">=","<="):
                where_parts.append(f"{col} {c.op} ?"); params.append(c.val)
            elif c.op=="IN":
                ph=",".join(["?"]*len(c.val)) if c.val else "NULL"
                where_parts.append(f"{col} IN ({ph})"); params.extend(c.val or [])
            elif c.op=="NOT IN":
                ph=",".join(["?"]*len(c.val)) if c.val else "NULL"
                where_parts.append(f"{col} NOT IN ({ph})"); params.extend(c.val or [])
            elif c.op=="IS NULL": where_parts.append(f"{col} IS NULL")
            elif c.op=="IS NOT NULL": where_parts.append(f"{col} IS NOT NULL")

        where_str = (" WHERE " + " AND ".join(where_parts)) if where_parts else ""
        join_str = (" AND " + " AND ".join(join_conds)) if join_conds else ""
        if join_str and where_parts: where_str = " WHERE " + " AND ".join(where_parts + join_conds)
        elif join_conds: where_str = " WHERE " + " AND ".join(join_conds)

        sql = f"SELECT {sel_str} FROM {from_str}{where_str}"

        # ORDER BY
        if ast.order:
            ord_parts=[]
            for o in ast.order:
                col=self._resolve_col(o.expr, var_map) or o.expr
                ord_parts.append(f"{col} {o.dir}")
            sql += " ORDER BY "+", ".join(ord_parts)

        # LIMIT
        if ast.limit: sql += f" LIMIT {ast.limit}"

        return sql, params

    def _resolve_col(self, expr: str, var_map: dict) -> str:
        """n.property → table_alias.column"""
        if "." in expr:
            var, prop = expr.split(".", 1)
            if var in var_map:
                al, kind = var_map[var]
                cols = NODE_COLS if kind == "node" else EDGE_COLS
                return f"{al}.{cols.get(prop, prop)}"
        return expr

    # ── 内存执行 (CodeGraph 回退) ──

    def _run_mem(self, ast: CypherAST) -> dict:
        if not self._gr: return {"error":"No graph or database available","results":[]}
        g = self._gr

        # 收集候选节点/边
        rows=[]
        for lp, rp, rp2 in ast.match.pats:
            # 筛选左节点
            left_nodes=self._filter_nodes(g, lp.labels, lp.var)
            if not left_nodes: continue
            # 如果没有关系，直接返回节点
            if not rp:
                rows.extend([{"n": n} for n in left_nodes])
                continue
            # 筛选关系
            rel_edges=self._filter_edges(g, rp.types, rp.var)
            right_nodes = self._filter_nodes(g, rp2.labels if rp2 else [], rp2.var if rp2 else "")
            if not rel_edges: continue
            # 连接
            for le in left_nodes:
                lid=le.id if hasattr(le,'id') else le.get('id','')
                for re in rel_edges:
                    sid=re.source_id if hasattr(re,'source_id') else re.get('source_id','')
                    tid=re.target_id if hasattr(re,'target_id') else re.get('target_id','')
                    if sid!=lid: continue
                    for ri in (right_nodes or [None]):
                        if ri:
                            rid=ri.id if hasattr(ri,'id') else ri.get('id','')
                            if tid!=rid: continue
                        row={"n":le,"r":re}
                        if ri: row["m"]=ri
                        rows.append(row)

        # WHERE 过滤
        rows=self._apply_where(rows, ast.where_conds)

        # ORDER BY
        if ast.order:
            for o in reversed(ast.order):
                rows.sort(key=lambda r,k=o.expr: self._row_val(r,k), reverse=(o.dir=="DESC"))

        # LIMIT
        total=len(rows)
        if ast.limit: rows=rows[:ast.limit]

        # RETURN 投影
        results=[]
        if not ast.ret:
            results=[{"n": self._node_to_dict(r.get("n"))} for r in rows]
        else:
            for r in rows:
                out={}
                for it in ast.ret:
                    if it.expr=="*":
                        for k,v in r.items():
                            out[k]=self._to_dict(v)
                    elif it.expr.startswith("count("):
                        out[it.alias or "count(*)"]=total
                    else:
                        val=self._row_val(r, it.expr)
                        out[it.alias or it.expr]=val
                results.append(out)

        return {"results": results, "total": total, "has_more": ast.limit is not None and len(results)>=(ast.limit or 0)}

    def _filter_nodes(self, g, labels, var) -> list:
        nodes=list(g._nodes.values())
        if labels:
            nodes=[n for n in nodes if str(n.node_type) in labels]
        return nodes

    def _filter_edges(self, g, types, var) -> list:
        edges=list(g._edges)
        if types: edges=[e for e in edges if str(e.edge_type) in types]
        return edges

    def _apply_where(self, rows, conds):
        if not conds: return rows
        out=[]
        for r in rows:
            ok=True
            for c in conds:
                val=self._row_val(r, c.col)
                if c.op=="CONTAINS": ok = c.val.lower() in str(val).lower()
                elif c.op=="=": ok = str(val)==str(c.val)
                elif c.op=="!=": ok = str(val)!=str(c.val)
                elif c.op=="IN": ok = str(val) in [str(x) for x in (c.val or [])]
                elif c.op=="NOT IN": ok = str(val) not in [str(x) for x in (c.val or [])]
                elif c.op=="IS NULL": ok = val is None
                elif c.op=="IS NOT NULL": ok = val is not None
                if not ok: break
            if ok: out.append(r)
        return out

    def _row_val(self, r, path):
        parts=path.split(".")
        obj=r.get(parts[0])
        if not obj or len(parts)==1:
            if hasattr(obj,'name'): return obj.name
            if isinstance(obj,dict): return obj.get('name','')
            return str(obj) if obj else ''
        prop=parts[1]
        # Node object
        if hasattr(obj,'__dataclass_fields__'):
            return getattr(obj, prop, '')
        # Edge object
        if hasattr(obj, prop): return getattr(obj, prop)
        # dict
        if isinstance(obj, dict): return obj.get(prop, '')
        return ''

    def _node_to_dict(self, n):
        if n is None: return {}
        if hasattr(n,'to_dict'): return n.to_dict()
        if isinstance(n,dict): return n
        return {"name":str(n)}

    def _to_dict(self, v):
        if v is None: return {}
        if hasattr(v,'to_dict'): return v.to_dict()
        if isinstance(v,dict): return v
        return str(v)


# ═══ 便捷 API ═══

def query_graph(query_text: str, db_path: str = "", graph: Any = None) -> dict:
    """执行 Cypher 查询"""
    return QueryEngine(db_path=db_path, graph=graph).execute(query_text)
