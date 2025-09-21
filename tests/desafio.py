from fastapi import FastAPI, HTTPException, Depends, Query, status
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, and_
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import IntegrityError
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
import uuid

# Configuração do banco de dados SQLite
SQLALCHEMY_DATABASE_URL = "sqlite:///./produtos.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Model do SQLAlchemy
class ProdutoModel(Base):
    __tablename__ = "produtos"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    nome = Column(String, nullable=False)
    descricao = Column(String)
    preco = Column(Float, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

# Criar as tabelas
Base.metadata.create_all(bind=engine)

# Pydantic Models
class ProdutoBase(BaseModel):
    nome: str
    descricao: Optional[str] = None
    preco: float

class ProdutoCreate(ProdutoBase):
    pass

class ProdutoUpdate(BaseModel):
    nome: Optional[str] = None
    descricao: Optional[str] = None
    preco: Optional[float] = None
    updated_at: Optional[datetime] = None

class ProdutoResponse(ProdutoBase):
    id: str
    created_at: datetime
    updated_at: datetime
    
    class Config:
        orm_mode = True

# Dependência para obter a sessão do banco de dados
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Inicializar a aplicação FastAPI
app = FastAPI(title="API de Produtos")

# Custom Exceptions
class ProdutoNotFound(Exception):
    """Exceção para quando um produto não é encontrado"""
    pass

class DatabaseError(Exception):
    """Exceção para erros genéricos de banco de dados"""
    pass

# Exception Handlers
@app.exception_handler(ProdutoNotFound)
async def produto_not_found_handler(request, exc):
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Produto não encontrado"
    )

@app.exception_handler(DatabaseError)
async def database_error_handler(request, exc):
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Erro interno do banco de dados"
    )

# Endpoints
@app.post("/produtos", response_model=ProdutoResponse, status_code=status.HTTP_201_CREATED)
def create_produto(produto: ProdutoCreate, db: Session = Depends(get_db)):
    try:
        db_produto = ProdutoModel(**produto.dict())
        db.add(db_produto)
        db.commit()
        db.refresh(db_produto)
        return db_produto
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Erro ao criar produto: {str(e)}"
        )
    except Exception as e:
        db.rollback()
        raise DatabaseError(f"Erro inesperado ao criar produto: {str(e)}")

@app.get("/produtos", response_model=List[ProdutoResponse])
def get_produtos(
    db: Session = Depends(get_db),
    preco_min: Optional[float] = Query(None, description="Preço mínimo"),
    preco_max: Optional[float] = Query(None, description="Preço máximo"),
    nome: Optional[str] = Query(None, description="Filtrar por nome")
):
    try:
        query = db.query(ProdutoModel)
        
        # Aplicar filtro de preço (price > 5000 and price < 8000) ou outros valores
        if preco_min is not None and preco_max is not None:
            query = query.filter(and_(ProdutoModel.preco > preco_min, ProdutoModel.preco < preco_max))
        elif preco_min is not None:
            query = query.filter(ProdutoModel.preco > preco_min)
        elif preco_max is not None:
            query = query.filter(ProdutoModel.preco < preco_max)
        
        # Filtro por nome
        if nome:
            query = query.filter(ProdutoModel.nome.ilike(f"%{nome}%"))
        
        return query.all()
    except Exception as e:
        raise DatabaseError(f"Erro ao buscar produtos: {str(e)}")

@app.get("/produtos/{produto_id}", response_model=ProdutoResponse)
def get_produto(produto_id: str, db: Session = Depends(get_db)):
    try:
        produto = db.query(ProdutoModel).filter(ProdutoModel.id == produto_id).first()
        if produto is None:
            raise ProdutoNotFound()
        return produto
    except ProdutoNotFound:
        raise
    except Exception as e:
        raise DatabaseError(f"Erro ao buscar produto: {str(e)}")

@app.patch("/produtos/{produto_id}", response_model=ProdutoResponse)
def update_produto(produto_id: str, produto_update: ProdutoUpdate, db: Session = Depends(get_db)):
    try:
        # Verificar se o produto existe
        db_produto = db.query(ProdutoModel).filter(ProdutoModel.id == produto_id).first()
        if db_produto is None:
            raise ProdutoNotFound()
        
        # Atualizar os campos
        update_data = produto_update.dict(exclude_unset=True)
        
        # Se updated_at não foi fornecido, usar o tempo atual
        if 'updated_at' not in update_data:
            update_data['updated_at'] = datetime.utcnow()
        
        for field, value in update_data.items():
            setattr(db_produto, field, value)
        
        db.commit()
        db.refresh(db_produto)
        return db_produto
    except ProdutoNotFound:
        raise
    except Exception as e:
        db.rollback()
        raise DatabaseError(f"Erro ao atualizar produto: {str(e)}")

@app.delete("/produtos/{produto_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_produto(produto_id: str, db: Session = Depends(get_db)):
    try:
        produto = db.query(ProdutoModel).filter(ProdutoModel.id == produto_id).first()
        if produto is None:
            raise ProdutoNotFound()
        
        db.delete(produto)
        db.commit()
    except ProdutoNotFound:
        raise
    except Exception as e:
        db.rollback()
        raise DatabaseError(f"Erro ao deletar produto: {str(e)}")

# Popular o banco com alguns dados iniciais
@app.on_event("startup")
def startup_event():
    db = SessionLocal()
    
    try:
        # Verificar se já existem dados
        if not db.query(ProdutoModel).first():
            # Criar produtos com preços diferentes
            produtos = [
                ProdutoModel(nome="Notebook Gamer", descricao="Notebook para jogos", preco=4500.00),
                ProdutoModel(nome="Smartphone Premium", descricao="Celular top de linha", preco=3500.00),
                ProdutoModel(nome="TV 55\" 4K", descricao="TV Ultra HD", preco=6000.00),
                ProdutoModel(nome="Geladeira Frost Free", descricao="Geladeira duplex", preco=5500.00),
                ProdutoModel(nome="Máquina de Lavar", descricao="Lava e seca", preco=7500.00),
                ProdutoModel(nome="PlayStation 5", descricao="Console de última geração", preco=8000.00),
                ProdutoModel(nome="Microondas", descricao="Microondas 30L", preco=2500.00),
                ProdutoModel(nome="Tablet", descricao="Tablet 10 polegadas", preco=7000.00),
                ProdutoModel(nome="Câmera DSLR", descricao="Câmera profissional", preco=9000.00),
                ProdutoModel(nome="Fone de Ouvido", descricao="Fone Bluetooth", preco=1500.00)
            ]
            db.add_all(produtos)
            db.commit()
    except Exception as e:
        print(f"Erro ao popular banco de dados: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
