import React, { useMemo } from 'react';
import { Instance, Instances } from '@react-three/drei';
import * as THREE from 'three';
import type { GroupProps } from '@react-three/fiber';
import type { Cadeira, StatusCadeira } from '../lib/types';
import { COR_CADEIRA } from '../lib/theme';

/* ------------------------------------------------------------------ *
 * Carteira individual - usada em destaques e inspecao de sala.
 * ------------------------------------------------------------------ */

// Object3D ja possui um `id` numerico: omitimos para expor o id da cadeira.
interface ChairProps extends Omit<GroupProps, 'id'> {
  id: string;
  status: StatusCadeira;
  onClickChair?: (id: string) => void;
}

export const ChairNode: React.FC<ChairProps> = ({
  id,
  status,
  onClickChair,
  position,
  ...props
}) => {
  const chairColor = COR_CADEIRA[status] ?? COR_CADEIRA.LIVRE;

  return (
    <group position={position} onClick={() => onClickChair?.(id)} {...props}>
      {/* Assento da carteira */}
      <mesh position={[0, 0.4, 0]} castShadow>
        <boxGeometry args={[0.5, 0.08, 0.5]} />
        <meshStandardMaterial color={chairColor} roughness={0.3} metalness={0.2} />
      </mesh>

      {/* Encosto da carteira */}
      <mesh position={[0, 0.7, -0.22]}>
        <boxGeometry args={[0.5, 0.5, 0.05]} />
        <meshStandardMaterial color={chairColor} roughness={0.4} />
      </mesh>

      {/* Base / pes metalicos */}
      <mesh position={[0, 0.2, 0]}>
        <cylinderGeometry args={[0.03, 0.03, 0.4, 8]} />
        <meshStandardMaterial color="#30363d" metalness={0.6} roughness={0.4} />
      </mesh>
    </group>
  );
};

/* ------------------------------------------------------------------ *
 * Campo instanciado - todas as carteiras do campus em 3 draw calls.
 * ------------------------------------------------------------------ */

interface CampoProps {
  cadeiras: Cadeira[];
  statusPorId: Record<string, StatusCadeira>;
  offsetY: number;
  onSelecionarSala?: (salaId: string) => void;
  atenuado?: boolean;
}

export const CampoDeCadeiras: React.FC<CampoProps> = ({
  cadeiras,
  statusPorId,
  offsetY,
  onSelecionarSala,
  atenuado = false,
}) => {
  const geoAssento = useMemo(() => new THREE.BoxGeometry(0.5, 0.08, 0.5), []);
  const geoEncosto = useMemo(() => new THREE.BoxGeometry(0.5, 0.45, 0.05), []);
  const geoBase = useMemo(() => new THREE.CylinderGeometry(0.035, 0.035, 0.4, 6), []);

  const limite = Math.max(cadeiras.length, 1);

  const cores = useMemo(
    () => cadeiras.map((c) => COR_CADEIRA[statusPorId[c.id] ?? c.status] ?? COR_CADEIRA.LIVRE),
    [cadeiras, statusPorId],
  );

  const opacidade = atenuado ? 0.32 : 1;

  return (
    <group>
      <Instances geometry={geoAssento} limit={limite} castShadow>
        <meshStandardMaterial
          roughness={0.32}
          metalness={0.24}
          transparent={atenuado}
          opacity={opacidade}
        />
        {cadeiras.map((c, i) => (
          <Instance
            key={c.id}
            color={cores[i]}
            position={[c.posicao.x, c.posicao.y + offsetY + 0.4, c.posicao.z]}
            onClick={(e) => {
              e.stopPropagation();
              onSelecionarSala?.(c.sala_id);
            }}
          />
        ))}
      </Instances>

      <Instances geometry={geoEncosto} limit={limite}>
        <meshStandardMaterial
          roughness={0.45}
          transparent={atenuado}
          opacity={opacidade}
        />
        {cadeiras.map((c, i) => (
          <Instance
            key={c.id}
            color={cores[i]}
            position={[c.posicao.x, c.posicao.y + offsetY + 0.66, c.posicao.z - 0.22]}
          />
        ))}
      </Instances>

      <Instances geometry={geoBase} limit={limite}>
        <meshStandardMaterial
          color="#39424e"
          metalness={0.55}
          roughness={0.45}
          transparent={atenuado}
          opacity={opacidade}
        />
        {cadeiras.map((c) => (
          <Instance
            key={c.id}
            position={[c.posicao.x, c.posicao.y + offsetY + 0.2, c.posicao.z]}
          />
        ))}
      </Instances>
    </group>
  );
};
